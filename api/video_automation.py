import os
import time
import json
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Tuple, List

try:
    import cv2
except ImportError:
    cv2 = None

try:
    from api.logger import system_logger, vision_logger
    from api.database import (
        db_get_all_residents,
        db_get_camera_config,
        db_get_telegram_config,
        db_get_ai_config,
        db_record_automation_run,
        db_is_event_already_notified,
        db_mark_event_notified,
        get_user_profile
    )
    from api.telegram_bot import send_telegram_photo, send_telegram_message
    from api.tools.vision_tools import capture_camera_frame, analyze_image_with_vision, set_vision_context
    from api.tools.mqtt_tools import controlar_luzes
except ImportError:
    from logger import system_logger, vision_logger
    from database import (
        db_get_all_residents,
        db_get_camera_config,
        db_get_telegram_config,
        db_get_ai_config,
        db_record_automation_run,
        db_is_event_already_notified,
        db_mark_event_notified,
        get_user_profile
    )
    from telegram_bot import send_telegram_photo, send_telegram_message
    from tools.vision_tools import capture_camera_frame, analyze_image_with_vision, set_vision_context
    from tools.mqtt_tools import controlar_luzes


# Cache em memória para cooldown entre notificações de vídeo
# Formato: { "auto_id_event_key": timestamp_float }
_VIDEO_COOLDOWN_CACHE: Dict[str, float] = {}

MODEL_DIR = os.path.join(os.path.dirname(__file__), "models")
YUNET_MODEL_PATH = os.path.join(MODEL_DIR, "face_detection_yunet_2023mar.onnx")
_YUNET_DETECTOR = None
_LAST_DETECTOR_SIZE = (0, 0)


def _ensure_yunet_model_downloaded() -> bool:
    """Garante que o modelo ONNX leve (230KB) do YuNet esteja baixado localmente para o OpenCV."""
    if os.path.exists(YUNET_MODEL_PATH) and os.path.getsize(YUNET_MODEL_PATH) > 100000:
        return True
    try:
        os.makedirs(MODEL_DIR, exist_ok=True)
        import urllib.request
        url = "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp, open(YUNET_MODEL_PATH, "wb") as f:
            f.write(resp.read())
        return os.path.exists(YUNET_MODEL_PATH) and os.path.getsize(YUNET_MODEL_PATH) > 100000
    except Exception as e:
        vision_logger.warning(f"[OpenCV Pre-Filter] Falha ao baixar modelo YuNet: {e}")
        return False


def opencv_detect_person_or_face(
    frame_bytes: bytes, 
    detection_mode: str = "video_face_recognition",
    min_confidence: float = 0.55
) -> Tuple[bool, int, str]:
    """
    Pré-filtro OpenCV para detectar se há pessoa ou rosto no quadro ANTES de chamar a IA Vision.
    Economiza 100% de tokens e requisições à nuvem quando o ambiente estiver vazio.
    """
    global _YUNET_DETECTOR, _LAST_DETECTOR_SIZE
    if not frame_bytes or cv2 is None:
        return True, 1, "OpenCV não disponível (bypass para IA)"

    try:
        import numpy as np
        nparr = np.frombuffer(frame_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None or img.size == 0:
            return False, 0, "Falha ao decodificar imagem"

        h, w = img.shape[:2]

        # 1. Verificação de luminosidade e variância (ignora quadros pretos/sem sinal)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        mean_bright = np.mean(gray)
        std_dev = np.std(gray)
        if mean_bright < 6.0 or std_dev < 6.0:
            return False, 0, "Quadro sem sinal ou excessivamente escuro"

        # 2. Detecção Facial de Alta Velocidade via OpenCV YuNet
        if _ensure_yunet_model_downloaded() and hasattr(cv2, "FaceDetectorYN"):
            try:
                if _YUNET_DETECTOR is None:
                    _YUNET_DETECTOR = cv2.FaceDetectorYN.create(
                        model=YUNET_MODEL_PATH,
                        config="",
                        input_size=(w, h),
                        score_threshold=min_confidence,
                        nms_threshold=0.3
                    )
                    _LAST_DETECTOR_SIZE = (w, h)
                elif _LAST_DETECTOR_SIZE != (w, h):
                    _YUNET_DETECTOR.setInputSize((w, h))
                    _LAST_DETECTOR_SIZE = (w, h)

                retval, faces = _YUNET_DETECTOR.detect(img)
                if faces is not None and len(faces) > 0:
                    valid_faces = [f for f in faces if f[-1] >= min_confidence]
                    if len(valid_faces) > 0:
                        conf = valid_faces[0][-1]
                        return True, len(valid_faces), f"{len(valid_faces)} rosto(s) detectado(s) via OpenCV YuNet (Confiança: {conf:.2f})"
            except Exception as e_yunet:
                vision_logger.warning(f"[OpenCV Pre-Filter] Erro no detector YuNet: {e_yunet}")

        # 3. Análise de Presença Humana por Tom de Pele (HSV) e Contornos Corporais (para modo de presença geral)
        if detection_mode in ["video_presence_detection", "any_person"]:
            hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
            lower_skin = np.array([0, 20, 70], dtype=np.uint8)
            upper_skin = np.array([20, 255, 255], dtype=np.uint8)
            skin_mask = cv2.inRange(hsv, lower_skin, upper_skin)
            skin_percent = (np.count_nonzero(skin_mask) / (w * h)) * 100.0
            
            if skin_percent > 1.5:  # Pelo menos 1.5% da imagem com tons humanos
                return True, 1, f"Presença humana detectada via OpenCV (Área de pele: {skin_percent:.1f}%)"

        return False, 0, "Nenhum rosto ou pessoa detectada no quadro pelo OpenCV"

    except Exception as e_all:
        vision_logger.warning(f"[OpenCV Pre-Filter] Exceção na verificação: {e_all}")
        return True, 1, "Fallback OpenCV (bypass)"


def clear_video_cooldown(auto_id: Optional[int] = None):
    """Limpa o cache de cooldown de uma regra específica ou de todas."""
    global _VIDEO_COOLDOWN_CACHE
    if auto_id is None:
        _VIDEO_COOLDOWN_CACHE.clear()
        vision_logger.info("[VideoAutomation] Cache de cooldown de vídeo reiniciado.")
    else:
        keys_to_del = [k for k in _VIDEO_COOLDOWN_CACHE if k.startswith(f"{auto_id}_")]
        for k in keys_to_del:
            _VIDEO_COOLDOWN_CACHE.pop(k, None)
        vision_logger.info(f"[VideoAutomation] Cooldown reiniciado para a regra ID {auto_id}.")


def evaluate_video_automation(rule: Dict[str, Any], now_local: datetime, is_manual: bool = False) -> Tuple[bool, str]:
    """
    Executa a análise de visão computacional e reconhecimento facial para uma regra de automação de vídeo.
    
    Tipos suportados:
    - video_face_recognition (Encontrar / Identificar morador específico ou qualquer morador)
    - video_unknown_alert (Alerta de pessoa não cadastrada / visitante / intruso)
    - video_presence_detection (Detecção geral de presença humana)
    """
    auto_id = rule.get("id")
    user_email = rule.get("user_email", "")
    rule_name = rule.get("name", "Automação de Vídeo")
    auto_type = rule.get("automation_type", "video_face_recognition")
    payload = rule.get("action_payload", {}) or {}
    
    target_person = str(payload.get("target_person") or "todos").strip()
    detection_mode = str(payload.get("detection_mode") or auto_type).strip()
    cooldown_seconds = int(payload.get("cooldown_seconds") if payload.get("cooldown_seconds") is not None else 300)
    notify_telegram = payload.get("notify_telegram", True)
    mqtt_room = payload.get("mqtt_room", "")
    mqtt_action = payload.get("mqtt_action", "")
    custom_msg = payload.get("custom_message", "")
    
    vision_logger.info(f"[VideoAutomation] Processando regra '{rule_name}' (ID {auto_id}) - Modo: {detection_mode}, Alvo: {target_person}")
    
    # 1. Captura o quadro atual da câmera configurada
    cam_cfg = db_get_camera_config(user_email)
    frame_bytes, err = capture_camera_frame(cam_cfg)
    
    if not frame_bytes:
        msg = f"Câmera inacessível: {err or 'Não foi possível capturar o quadro de vídeo.'}"
        vision_logger.warning(f"[VideoAutomation] {msg}")
        if is_manual:
            db_record_automation_run(auto_id, "error", msg)
        return False, msg

    # 2. Pré-filtro Inteligente Local com OpenCV (Economia de 100% dos tokens do Gemini se vazio)
    has_person, face_count, opencv_details = opencv_detect_person_or_face(
        frame_bytes, 
        detection_mode=detection_mode,
        min_confidence=0.5
    )
    
    if not has_person and not is_manual:
        msg = f"Nenhuma pessoa ou rosto detectado no frame pelo OpenCV ({opencv_details}). Chamada à IA omitida para economizar tokens."
        vision_logger.info(f"[VideoAutomation] [OpenCV Pre-Filter] 🛡️ {msg}")
        return False, msg
    elif not has_person and is_manual:
        vision_logger.info(f"[VideoAutomation] [OpenCV Pre-Filter] {opencv_details} (Modo manual de teste: executando chamada à IA)")
    else:
        vision_logger.info(f"[VideoAutomation] [OpenCV Pre-Filter] 👤 {opencv_details}. Enviando quadro para identificação com IA Vision...")

    # 3. Recupera fotos cadastradas dos moradores no SQLite
    residents = db_get_all_residents()
    ref_images = []
    residents_info = []
    
    for r in residents:
        r_name = r.get("name", "Morador")
        r_email = r.get("email", "")
        if r.get("has_photo") and r.get("photo_base64"):
            ref_images.append({
                "label": f"Foto de Referência Oficial: {r_name} ({r_email})",
                "photo_base64": r["photo_base64"],
                "name": r_name,
                "email": r_email
            })
            residents_info.append(f"- Morador(a): {r_name} (E-mail: {r_email}, POSSUI foto cadastrada)")
        else:
            residents_info.append(f"- Morador(a): {r_name} (E-mail: {r_email}, SEM foto)")

    residents_summary = "\n".join(residents_info) if residents_info else "Nenhum morador cadastrado no sistema."

    # 4. Constrói o Prompt Estruturado de Reconhecimento Facial para a IA
    target_clause = ""
    if target_person.lower() not in ["todos", "qualquer", "all", ""]:
        target_clause = f"Atenção especial para o morador alvo: '{target_person}'."

    prompt = f"""Você é o sistema de visão e segurança inteligente da assistente residencial Sexta-Feira.
A Imagem 1 é a captura em tempo real da câmera de monitoramento da casa.
{target_clause}

Moradores oficiais cadastrados no sistema:
{residents_summary}

Regras estritas de análise:
1. Verifique se há uma ou mais pessoas visíveis na Imagem 1.
2. Se houver pessoas, compare os traços faciais com as fotos de referência dos moradores fornecidas nas imagens subsequentes.
3. Classifique a cena em um dos seguintes status no formato JSON exato:
- "PRESENCE_MATCH": Encontrou uma pessoa identificada como morador cadastrado. Indique o nome do morador no campo "person_name".
- "UNKNOWN_PERSON": Encontrou uma pessoa humana, mas o rosto NÃO coincide com nenhum dos moradores cadastrados (visitante/desconhecido).
- "NO_PERSON": O ambiente está livre / não há pessoas humanas visíveis.

Responda OBRIGATORIAMENTE no formato JSON puro:
{{
  "status": "PRESENCE_MATCH" | "UNKNOWN_PERSON" | "NO_PERSON",
  "person_name": "Nome do morador ou 'Desconhecido'",
  "confidence": "alta" | "media" | "baixa",
  "description": "Breve resumo do que a pessoa está fazendo (ex: acabou de entrar pela porta, está na sala, etc.)"
}}
"""

    ai_cfg = db_get_ai_config(user_email)
    user_prof = get_user_profile(user_email)
    api_key = (ai_cfg.get("api_key") or user_prof.get("api_key") or os.getenv("GEMINI_API_KEY") or "").strip()
    model_name = (ai_cfg.get("ai_model") or user_prof.get("ai_model") or os.getenv("DEFAULT_MODEL", "gemini-2.5-flash-lite")).strip()

    # Fallback para chave de perfil de morador no SQLite caso sub-conta não tenha chave configurada
    if not api_key:
        try:
            from api.database import get_db_connection
            conn = get_db_connection()
            c = conn.cursor()
            c.execute("SELECT api_key, ai_model FROM user_profiles WHERE api_key != '' AND api_key NOT LIKE 'fake%' AND api_key NOT LIKE '123%' LIMIT 1")
            row = c.fetchone()
            conn.close()
            if row and row["api_key"]:
                api_key = row["api_key"]
                if not model_name:
                    model_name = row["ai_model"]
        except Exception:
            pass

    # Se não tiver chave de IA configurada, não é possível avaliar reconhecimento
    if not api_key:
        msg = "Chave de API com suporte a visão não configurada para processar automação de vídeo."
        if is_manual:
            db_record_automation_run(auto_id, "error", msg)
        return False, msg

    set_vision_context(user_email=user_email, camera_config=cam_cfg, api_key=api_key, model_name=model_name)
    raw_response = analyze_image_with_vision(frame_bytes, prompt, reference_images=ref_images, api_key=api_key, model_name=model_name)
    vision_logger.info(f"[VideoAutomation] Resposta da IA de visão: {raw_response[:180]}...")

    # 5. Processamento do Resultado JSON
    parsed = {}
    try:
        clean_json_str = raw_response.strip()
        if "```json" in clean_json_str:
            clean_json_str = clean_json_str.split("```json")[1].split("```")[0].strip()
        elif "```" in clean_json_str:
            clean_json_str = clean_json_str.split("```")[1].split("```")[0].strip()
        parsed = json.loads(clean_json_str)
    except Exception as e_json:
        vision_logger.warning(f"[VideoAutomation] Falha ao fazer parse JSON da IA ({e_json}). Resposta bruta: {raw_response}")
        # Heurística de fallback em texto caso o modelo retorne texto corrido
        resp_lower = raw_response.lower()
        if any(r.get("name", "").lower() in resp_lower for r in residents if r.get("name")):
            matched_r = next((r["name"] for r in residents if r.get("name") and r["name"].lower() in resp_lower), "Morador")
            parsed = {"status": "PRESENCE_MATCH", "person_name": matched_r, "description": raw_response}
        elif "desconhecido" in resp_lower or "visitante" in resp_lower or "pessoa" in resp_lower:
            parsed = {"status": "UNKNOWN_PERSON", "person_name": "Desconhecido", "description": raw_response}
        else:
            parsed = {"status": "NO_PERSON", "person_name": "", "description": "Nenhuma pessoa detectada"}

    status_result = parsed.get("status", "NO_PERSON")
    detected_name = parsed.get("person_name", "").strip()
    scene_desc = parsed.get("description", "").strip()

    # 6. Avaliação das Condições de Disparo da Regra
    should_trigger = False
    event_identifier = ""
    notification_title = ""
    notification_body = ""

    # Condição A: Reconhecimento de Morador Específico / Qualquer Morador
    if detection_mode in ["video_face_recognition", "presence_match", "resident_arrival"]:
        if status_result == "PRESENCE_MATCH":
            if target_person.lower() in ["todos", "qualquer", "all", ""]:
                should_trigger = True
            elif target_person.lower() in detected_name.lower() or detected_name.lower() in target_person.lower():
                should_trigger = True
                
            if should_trigger:
                event_identifier = f"match_{detected_name.lower()}"
                notification_title = f"👤 Morador Identificado: {detected_name}"
                notification_body = custom_msg or f"O morador *{detected_name}* foi reconhecido na câmera da residência!"
                if scene_desc:
                    notification_body += f"\n_{scene_desc}_"

    # Condição B: Alerta de Visitante / Pessoa Desconhecida
    elif detection_mode in ["video_unknown_alert", "unknown_person", "intruder_alert"]:
        if status_result == "UNKNOWN_PERSON":
            should_trigger = True
            event_identifier = "unknown_person_detected"
            notification_title = "🚨 Alerta de Segurança: Pessoa Não Cadastrada"
            notification_body = custom_msg or "Uma pessoa não cadastrada / visitante foi identificada na câmera!"
            if scene_desc:
                notification_body += f"\n_{scene_desc}_"

    # Condição C: Detecção Geral de Qualquer Presença
    elif detection_mode in ["video_presence_detection", "any_person"]:
        if status_result in ["PRESENCE_MATCH", "UNKNOWN_PERSON"]:
            should_trigger = True
            who = detected_name if status_result == "PRESENCE_MATCH" else "Pessoa não cadastrada"
            event_identifier = f"presence_{who.lower()}"
            notification_title = f"👁️ Presença Detectada: {who}"
            notification_body = custom_msg or f"Movimento e presença humana ({who}) detectados na câmera."
            if scene_desc:
                notification_body += f"\n_{scene_desc}_"

    # Se não atendeu as condições de disparo
    if not should_trigger:
        vision_logger.info(f"[VideoAutomation] Regra '{rule_name}' não disparou (Status observado: {status_result}, Detectado: '{detected_name}')")
        if is_manual:
            msg = f"Nenhum disparo: {status_result} ('{detected_name}'). {scene_desc}"
            db_record_automation_run(auto_id, "success", msg)
            return True, msg
        return False, "Condição não satisfeita."

    # 7. Verificação de Cooldown Anti-Spam (Evita inundar o Telegram)
    now_ts = time.time()
    cache_key = f"{auto_id}_{event_identifier}"
    last_sent_ts = _VIDEO_COOLDOWN_CACHE.get(cache_key, 0.0)
    
    if not is_manual and (now_ts - last_sent_ts) < cooldown_seconds:
        remaining = int(cooldown_seconds - (now_ts - last_sent_ts))
        vision_logger.info(f"[VideoAutomation] Evento '{event_identifier}' em cooldown (restam {remaining}s). Notificação omitida.")
        return False, f"Em cooldown ({remaining}s restantes)."

    # Atualiza o timestamp de disparo
    _VIDEO_COOLDOWN_CACHE[cache_key] = now_ts

    # 8. Execução das Ações Configuradas
    execution_reports = []

    # Ação 1: Envio de Foto e Notificação no Telegram
    tg_cfg = db_get_telegram_config(user_email)
    bot_token = tg_cfg.get("bot_token", "")
    chat_id = tg_cfg.get("chat_id", "")
    
    if notify_telegram and bot_token and chat_id:
        caption = f"📹 *{notification_title}*\n{notification_body}\n\n⏱️ _{now_local.strftime('%d/%m/%Y às %H:%M:%S')}_"
        ok_photo, resp_photo = send_telegram_photo(bot_token, chat_id, frame_bytes, caption=caption)
        if ok_photo:
            execution_reports.append("Foto e alerta enviados com sucesso no Telegram")
            vision_logger.info(f"[VideoAutomation] Foto enviada no Telegram para chat {chat_id}")
        else:
            vision_logger.warning(f"[VideoAutomation] Falha ao enviar foto no Telegram: {resp_photo}. Tentando texto...")
            send_telegram_message(bot_token, chat_id, caption, parse_mode="Markdown")
            execution_reports.append(f"Aviso em texto enviado no Telegram (Falha na foto: {resp_photo})")
    elif notify_telegram:
        execution_reports.append("Telegram não configurado para envio de foto")

    agent_action_prompt = str(payload.get("agent_action_prompt") or payload.get("custom_action") or "").strip()

    # Ação 2: Acionamento Residencial Inteligente em Linguagem Natural (ex: 'Acender a luz do quarto', 'Ligar a luz de fora')
    if agent_action_prompt:
        try:
            try:
                from api.agent import processar_comando_agente
            except ImportError:
                from agent import processar_comando_agente

            broker_host = os.getenv("MQTT_BROKER", "test.mosquitto.org")
            broker_port = int(os.getenv("MQTT_PORT", "1883"))
            ai_cfg = db_get_ai_config(user_email)
            agent_name = (ai_cfg.get("agent_name") or "Sexta-Feira").strip()

            res_ag = processar_comando_agente(
                pergunta=agent_action_prompt,
                api_key=api_key,
                modelo=model_name,
                agent_name=agent_name,
                rooms=[],
                rooms_state={},
                broker_config={"broker": broker_host, "port": broker_port},
                user_email=user_email,
                user_profile=user_prof
            )
            reply_ag = res_ag.get("reply", "") if isinstance(res_ag, dict) else str(res_ag)
            execution_reports.append(f"Ação Residencial executada: '{agent_action_prompt}' ({reply_ag})")
            vision_logger.info(f"[VideoAutomation] Ação do Agente executada: '{agent_action_prompt}' -> {reply_ag}")
        except Exception as e_ag:
            vision_logger.warning(f"[VideoAutomation] Erro ao executar ação do agente: {e_ag}")

    # Ação 3: Acionamento Residencial MQTT legado (caso especificado como sala/OFF direto)
    elif mqtt_room and mqtt_action:
        try:
            res_mqtt = controlar_luzes.invoke({"room": mqtt_room, "action": mqtt_action.upper()})
            execution_reports.append(f"Comando residencial MQTT executado ({mqtt_room} -> {mqtt_action})")
            vision_logger.info(f"[VideoAutomation] MQTT disparado: {res_mqtt}")
        except Exception as e_mqtt:
            vision_logger.warning(f"[VideoAutomation] Erro na ação MQTT: {e_mqtt}")

    final_msg = f"Disparo executado com sucesso: {notification_title}. " + "; ".join(execution_reports)
    db_record_automation_run(auto_id, "success", final_msg)
    vision_logger.info(f"[VideoAutomation] {final_msg}")
    
    return True, final_msg

import os
import io
import time
import base64
from typing import Optional, Dict, Any, Tuple, List
from langchain_core.tools import tool

try:
    import cv2
except ImportError:
    cv2 = None

try:
    from PIL import Image
except ImportError:
    Image = None

import requests
from requests.auth import HTTPBasicAuth, HTTPDigestAuth

try:
    from api.logger import vision_logger
    from api.database import db_get_camera_config, db_get_all_residents, db_get_ai_config
except ImportError:
    from logger import vision_logger
    from database import db_get_camera_config, db_get_all_residents, db_get_ai_config

# =========================================================================
# CONTEXTO DE EXECUÇÃO DE VISÃO E CÂMERA DO USUÁRIO
# =========================================================================

_ACTIVE_VISION_USER: str = ""
_ACTIVE_CAMERA_CONFIG: Dict[str, Any] = {}
_ACTIVE_API_KEY: str = ""
_ACTIVE_MODEL: str = "gemini-2.5-flash"
_BROWSER_SNAPSHOTS: Dict[str, Tuple[bytes, float]] = {}  # {user_email: (bytes, timestamp)}

def set_vision_context(user_email: str = "", camera_config: Optional[Dict[str, Any]] = None, api_key: str = "", model_name: str = ""):
    """Configura o usuário ativo, suas configurações de câmera e chaves de IA para as tools de visão."""
    global _ACTIVE_VISION_USER, _ACTIVE_CAMERA_CONFIG, _ACTIVE_API_KEY, _ACTIVE_MODEL
    _ACTIVE_VISION_USER = (user_email or "").strip().lower()
    if api_key:
        _ACTIVE_API_KEY = api_key.strip()
    if model_name:
        _ACTIVE_MODEL = model_name.strip()
    if camera_config:
        _ACTIVE_CAMERA_CONFIG = camera_config
    elif _ACTIVE_VISION_USER:
        _ACTIVE_CAMERA_CONFIG = db_get_camera_config(_ACTIVE_VISION_USER)
    else:
        _ACTIVE_CAMERA_CONFIG = {}

def set_latest_browser_snapshot(user_email: str, image_bytes: bytes):
    """Armazena o último frame enviado pelo navegador do usuário."""
    clean_email = (user_email or "anonimo@smarthome.local").strip().lower()
    _BROWSER_SNAPSHOTS[clean_email] = (image_bytes, time.time())
    vision_logger.info(f"Snapshot do navegador recebido para usuário '{clean_email}' ({len(image_bytes)} bytes)")

def get_latest_browser_snapshot(user_email: str, max_age_seconds: float = 300.0) -> Optional[bytes]:
    """Recupera o último snapshot do navegador se dentro do limite de tempo."""
    clean_email = (user_email or "anonimo@smarthome.local").strip().lower()
    item = _BROWSER_SNAPSHOTS.get(clean_email)
    if not item:
        # Fallback para o primeiro snapshot disponível
        if _BROWSER_SNAPSHOTS:
            return next(iter(_BROWSER_SNAPSHOTS.values()))[0]
        return None
    data, ts = item
    if (time.time() - ts) <= max_age_seconds:
        return data
    return None

# =========================================================================
# MOTOR DE CAPTURA DE QUADROS (FRAME CAPTURE ENGINE)
# =========================================================================

def capture_camera_frame(config: Optional[Dict[str, Any]] = None) -> Tuple[Optional[bytes], Optional[str]]:
    """
    Captura um quadro (frame JPEG) da câmera configurada (Webcam local ou Câmera IP).
    Retorna (bytes_jpeg, mensagem_erro).
    """
    cfg = config or _ACTIVE_CAMERA_CONFIG
    if not cfg and _ACTIVE_VISION_USER:
        cfg = db_get_camera_config(_ACTIVE_VISION_USER)
    if not cfg:
        cfg = {"camera_type": "device", "camera_device_index": 0}

    camera_type = cfg.get("camera_type", "device")

    # 1. CÂMERA IP (RTSP / HTTP SNAPSHOT / MJPEG)
    if camera_type == "ip":
        ip_url = (cfg.get("camera_ip_url") or "").strip()
        username = (cfg.get("camera_username") or "").strip()
        password = (cfg.get("camera_password") or "").strip()

        if not ip_url:
            return None, "URL da Câmera IP não configurada nas opções do usuário."

        # A) Tentativa de HTTP/HTTPS Snapshot direto
        if ip_url.lower().startswith("http://") or ip_url.lower().startswith("https://"):
            try:
                auth = None
                if username and password:
                    auth = HTTPBasicAuth(username, password)
                
                resp = requests.get(ip_url, auth=auth, timeout=6)
                if resp.status_code == 401 and username and password:
                    # Tenta Digest Auth se Basic falhar
                    resp = requests.get(ip_url, auth=HTTPDigestAuth(username, password), timeout=6)

                if resp.status_code == 200 and resp.content:
                    # Valida se é JPEG válido
                    if resp.content.startswith(b'\xff\xd8') or "image" in resp.headers.get("Content-Type", ""):
                        return resp.content, None
            except Exception as e_http:
                vision_logger.warning(f"Snapshot HTTP da Câmera IP falhou: {e_http}")

        # B) Tentativa via OpenCV (RTSP / MJPEG stream)
        if cv2 is not None:
            try:
                cap_url = ip_url
                if username and password and "://" in ip_url and "@" not in ip_url:
                    protocol, rest = ip_url.split("://", 1)
                    cap_url = f"{protocol}://{username}:{password}@{rest}"

                cap = cv2.VideoCapture(cap_url)
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                if cap.isOpened():
                    ret, frame = cap.read()
                    cap.release()
                    if ret and frame is not None:
                        success, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
                        if success:
                            return buffer.tobytes(), None
            except Exception as e_cv:
                vision_logger.warning(f"Captura OpenCV da Câmera IP falhou: {e_cv}")

        return None, f"Não foi possível obter imagem da Câmera IP no endereço '{ip_url}'."

    # 2. CÂMERA DO DISPOSITIVO (WEBCAM LOCAL / BROWSER WEBCAM)
    device_index = int(cfg.get("camera_device_index", 0))
    vision_logger.info(f"Tentando capturar frame da Câmera Local (Dispositivo índice {device_index})")

    # Tentativa via OpenCV local
    if cv2 is not None:
        try:
            cap = cv2.VideoCapture(device_index)
            if cap.isOpened():
                for _ in range(3):
                    cap.read()
                ret, frame = cap.read()
                cap.release()
                if ret and frame is not None:
                    success, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
                    if success:
                        return buffer.tobytes(), None
        except Exception as e_dev:
            vision_logger.warning(f"Acesso à webcam local via OpenCV falhou: {e_dev}")

    # Fallback: snapshot enviado pelo navegador via interface web
    cached = get_latest_browser_snapshot(_ACTIVE_VISION_USER)
    if cached:
        vision_logger.info("Utilizando snapshot recebido pelo navegador do usuário.")
        return cached, None

    return None, "Câmera local não encontrada ou sem permissão de acesso no servidor/navegador."

# =========================================================================
# MOTOR DE VISÃO COMPUTACIONAL MULTIMODAL (LLM VISION)
# =========================================================================

def analyze_image_with_vision(
    image_bytes: bytes, 
    prompt: str, 
    reference_images: Optional[List[Dict[str, Any]]] = None,
    api_key: Optional[str] = None,
    model_name: Optional[str] = None
) -> str:
    """
    Analisa os bytes de imagem utilizando o modelo multimodal (Google Gemini Vision ou OpenAI GPT-4o).
    Suporta multi-imagem (ex: frame da câmera + fotos de referência dos moradores para reconhecimento facial).
    """
    global _ACTIVE_API_KEY, _ACTIVE_MODEL, _ACTIVE_VISION_USER
    target_key = (api_key or _ACTIVE_API_KEY or "").strip()
    target_model = (model_name or _ACTIVE_MODEL or "").strip()

    if not target_key and _ACTIVE_VISION_USER:
        user_ai_cfg = db_get_ai_config(_ACTIVE_VISION_USER)
        target_key = (user_ai_cfg.get("api_key") or "").strip()
        if not target_model:
            target_model = (user_ai_cfg.get("ai_model") or "gemini-2.5-flash-lite").strip()

    target_key = target_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or ""
    openai_key = os.getenv("OPENAI_API_KEY") or ""

    # Fallback para qualquer chave válida cadastrada no SQLite
    if not target_key:
        try:
            from api.database import get_db_connection
            conn = get_db_connection()
            c = conn.cursor()
            c.execute("SELECT api_key, ai_model FROM user_profiles WHERE api_key != '' AND api_key NOT LIKE 'fake%' AND api_key NOT LIKE '123%' LIMIT 1")
            row = c.fetchone()
            conn.close()
            if row and row["api_key"]:
                target_key = row["api_key"]
                if not target_model:
                    target_model = row["ai_model"]
        except Exception:
            pass
    
    if target_key and target_key.startswith("sk-"):
        openai_key = target_key
        target_key = ""
        
    base64_img = base64.b64encode(image_bytes).decode("utf-8")
    data_url = f"data:image/jpeg;base64,{base64_img}"
    
    # Monta payload de conteúdo multimodal
    content_list_gemini = [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": data_url}
    ]
    content_list_openai = [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": data_url}}
    ]
    
    if reference_images:
        for idx, ref in enumerate(reference_images, start=2):
            lbl = ref.get("label", f"Foto de Referência {idx}")
            raw_ref_b64 = ref.get("photo_base64", "")
            if raw_ref_b64:
                ref_url = raw_ref_b64 if raw_ref_b64.startswith("data:") else f"data:image/jpeg;base64,{raw_ref_b64}"
                content_list_gemini.append({"type": "text", "text": f"\n[Imagem {idx}: {lbl}]"})
                content_list_gemini.append({"type": "image_url", "image_url": ref_url})
                content_list_openai.append({"type": "text", "text": f"\n[Imagem {idx}: {lbl}]"})
                content_list_openai.append({"type": "image_url", "image_url": {"url": ref_url}})

    # 1. Tentativa com Google Gemini Vision
    if target_key:
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
            from langchain_core.messages import HumanMessage
            
            gemini_model = target_model if "gemini" in target_model else "gemini-2.5-flash"
            llm = ChatGoogleGenerativeAI(
                model=gemini_model,
                google_api_key=target_key,
                temperature=0.2
            )
            
            message = HumanMessage(content=content_list_gemini)
            resp = llm.invoke([message])
            content = resp.content if hasattr(resp, "content") else str(resp)
            if isinstance(content, list):
                content = " ".join([c.get("text", "") if isinstance(c, dict) else str(c) for c in content])
            return content.strip()
        except Exception as e_gemini:
            vision_logger.error(f"Erro no Gemini Vision: {e_gemini}")

    # 2. Fallback para OpenAI GPT-4o Vision
    if openai_key:
        try:
            from langchain_openai import ChatOpenAI
            from langchain_core.messages import HumanMessage
            
            llm = ChatOpenAI(
                model="gpt-4o-mini",
                openai_api_key=openai_key,
                temperature=0.2
            )
            
            message = HumanMessage(content=content_list_openai)
            resp = llm.invoke([message])
            content = resp.content if hasattr(resp, "content") else str(resp)
            return content.strip()
        except Exception as e_openai:
            vision_logger.error(f"Erro no OpenAI Vision: {e_openai}")

    return "Não foi possível analisar a imagem pois nenhuma chave de API válida com suporte a visão (Gemini ou OpenAI) foi configurada."

# =========================================================================
# FERRAMENTAS LANGCHAIN DE VISÃO E CÂMERA
# =========================================================================

@tool
def ver_camera(solicitacao: str = "Descreva detalhadamente o que você está vendo no ambiente") -> str:
    """
    Acessa a câmera (webcam local ou câmera IP configurada) em tempo real, captura uma foto do ambiente
    e analisa a imagem com inteligência artificial para descrever o que está acontecendo, objetos,
    iluminação ou responder a perguntas visuais do usuário.
    
    Args:
        solicitacao: A pergunta ou foco do que deve ser analisado e descrito (ex: 'O que tem na mesa?', 'As luzes estão acesas?').
    """
    vision_logger.info(f"Executando tool ver_camera com solicitação: '{solicitacao}'")
    
    frame_bytes, err = capture_camera_frame()
    if not frame_bytes:
        return f"Aviso de Câmera: {err or 'Não foi possível capturar imagem da câmera no momento.'}"
        
    system_prompt = (
        "Você é o sistema de visão computacional da assistente residencial Sexta-Feira. "
        "Analise a imagem da câmera e responda em português brasileiro de forma natural, concisa e acolhedora. "
        "Evite formatação Markdown como asteriscos ou negrito para que o sintetizador de voz (TTS) fale de forma fluida. "
        f"Instrução específica do usuário: {solicitacao}"
    )
    
    return analyze_image_with_vision(frame_bytes, system_prompt)


@tool
def detectar_e_cumprimentar_pessoas(saudacao_personalizada: str = "") -> str:
    """
    Verifica a câmera do ambiente para identificar a presença de pessoas.
    Se encontrar alguém, compara as características faciais com as fotos cadastradas dos moradores da casa:
    - Se for um morador cadastrado: cumprimenta a pessoa pelo nome (ex: 'Olá, Marcio! Seja bem-vindo à sua casa.') e confirma que é morador oficial.
    - Se for alguém não cadastrado / visitante: cumprimenta educadamente como visitante informando que não encontrou cadastro de morador.
    - Se o ambiente estiver vazio: informa que o cômodo está livre no momento.
    
    Args:
        saudacao_personalizada: Instrução extra de cumprimento se fornecida pelo usuário.
    """
    vision_logger.info("Executando tool detectar_e_cumprimentar_pessoas com verificação de moradores")
    
    frame_bytes, err = capture_camera_frame()
    if not frame_bytes:
        return f"Aviso de Câmera: {err or 'Não foi possível acessar a câmera para verificar a presença de pessoas.'}"
        
    residents = db_get_all_residents()
    ref_images = []
    residents_desc = []
    for r in residents:
        if r.get("has_photo") and r.get("photo_base64"):
            ref_images.append({
                "label": f"Foto de Referência do Morador Oficial: {r['name']} (E-mail: {r['email']})",
                "photo_base64": r["photo_base64"]
            })
            residents_desc.append(f"- Morador(a): {r['name']} (E-mail: {r['email']}, possui foto de referência)")
        else:
            residents_desc.append(f"- Morador(a): {r['name']} (E-mail: {r['email']}, sem foto cadastrada)")
            
    residents_text = "\n".join(residents_desc) if residents_desc else "Nenhum morador possui foto cadastrada no sistema."
    
    prompt = (
        "Você é a assistente residencial inteligente Sexta-Feira. "
        "A Imagem 1 fornecida é a captura ao vivo da câmera do cômodo da casa. "
        f"Abaixo está a lista de moradores oficiais cadastrados na residência:\n{residents_text}\n"
    )
    if ref_images:
        prompt += (
            f"As imagens seguintes (Imagem 2 em diante) são as fotos de referência facial dos moradores oficiais cadastrados. "
            "Examine minuciosamente a Imagem 1 (câmera ao vivo) e compare os rostos das pessoas presentes com as fotos de referência dos moradores. "
            "Regras de avaliação:\n"
            "1. Se houver pessoa e o rosto coincidir com a foto de referência de um morador cadastrado: "
            "cumprimente o morador calorosamente pelo nome próprio e confirme com naturalidade que você o reconheceu como morador da casa.\n"
            "2. Se houver pessoa, mas o rosto NÃO coincidir com nenhum morador cadastrado (ou se o morador não tiver foto): "
            "cumprimente com educação e cordialidade, mas avise que identificou que a pessoa não possui cadastro de morador da casa (tratando-a como visitante).\n"
            "3. Se NÃO houver ninguém na Imagem 1 (ambiente vazio): informe de forma simpática que o cômodo está livre no momento.\n"
        )
    else:
        prompt += (
            "Como nenhum morador cadastrou foto de perfil ainda, identifique se há pessoas na Imagem 1. "
            "Se houver alguém, cumprimente a pessoa e mencione amigavelmente que, caso ela seja moradora, pode cadastrar sua foto na tela de Perfil para ser reconhecida pelo nome no futuro. "
            "Se o cômodo estiver vazio, informe que não há ninguém no local."
        )
        
    prompt += (
        "\nResponda sempre em TEXTO PURO (sem asteriscos, títulos '#' ou formatação markdown), em tom natural e acolhedor em português brasileiro para leitura por voz (TTS)."
    )
    if saudacao_personalizada:
        prompt += f" Instrução extra: {saudacao_personalizada}"
        
    return analyze_image_with_vision(frame_bytes, prompt, reference_images=ref_images)


@tool
def identificar_morador_ou_visitante(detalhes_solicitados: str = "") -> str:
    """
    Examina a câmera do ambiente e avalia formalmente a identidade de quem está presente,
    comparando os traços faciais com o banco de fotos dos moradores cadastrados da residência.
    Retorna se a pessoa presente é um Morador Oficial (informando o nome) ou um Visitante / Pessoa Não Cadastrada.
    
    Args:
        detalhes_solicitados: Informação ou pergunta específica sobre quem está no cômodo (ex: 'O morador Marcio está na sala?', 'Quem é a pessoa filmada?').
    """
    vision_logger.info("Executando tool identificar_morador_ou_visitante")
    
    frame_bytes, err = capture_camera_frame()
    if not frame_bytes:
        return f"Aviso de Câmera: {err or 'Não foi possível acessar a câmera para avaliar a identidade das pessoas.'}"
        
    residents = db_get_all_residents()
    ref_images = []
    residents_desc = []
    for r in residents:
        if r.get("has_photo") and r.get("photo_base64"):
            ref_images.append({
                "label": f"Foto Facial de Referência: Morador {r['name']}",
                "photo_base64": r["photo_base64"]
            })
            residents_desc.append(f"- Morador: {r['name']} (E-mail: {r['email']}, foto cadastrada)")
        else:
            residents_desc.append(f"- Morador: {r['name']} (E-mail: {r['email']}, sem foto)")
            
    residents_text = "\n".join(residents_desc) if residents_desc else "Nenhum morador possui foto cadastrada."
    
    prompt = (
        "Você é o módulo de reconhecimento e segurança da assistente residencial Sexta-Feira. "
        "A Imagem 1 é a câmera ao vivo do cômodo da casa. "
        f"Moradores cadastrados na casa:\n{residents_text}\n"
    )
    if ref_images:
        prompt += (
            "As imagens adicionais trazem as fotos dos moradores cadastrados. "
            "Compare o rosto da pessoa na Imagem 1 com as fotos de referência. "
            "Determine com precisão:\n"
            "- Se a pessoa for um morador cadastrado: informe o nome do morador e confirme que ele é morador oficial da residência.\n"
            "- Se a pessoa NÃO for um morador cadastrado: informe com clareza que trata-se de um visitante ou pessoa não cadastrada no sistema.\n"
            "- Se o ambiente estiver vazio: informe que não há ninguém presente no local.\n"
        )
    else:
        prompt += (
            "Nenhum morador possui foto de referência cadastrada no sistema. Avalie se há pessoas na imagem e relate o que você vê."
        )
        
    prompt += "\nResponda em texto puro e natural em português brasileiro, sem qualquer formatação markdown ou asteriscos."
    if detalhes_solicitados:
        prompt += f" Pergunta do usuário: {detalhes_solicitados}"
        
    return analyze_image_with_vision(frame_bytes, prompt, reference_images=ref_images)


@tool
def status_camera() -> str:
    """
    Verifica e retorna o status da câmera cadastrada no sistema (se é uma Câmera Local ou Câmera IP, 
    endereço configurado e se o acesso está funcionando).
    """
    cfg = _ACTIVE_CAMERA_CONFIG
    if not cfg and _ACTIVE_VISION_USER:
        cfg = db_get_camera_config(_ACTIVE_VISION_USER)
        
    cam_type = cfg.get("camera_type", "device")
    ip_url = cfg.get("camera_ip_url", "")
    auto_greet = cfg.get("camera_auto_greeting", True)
    
    tipo_desc = "Câmera IP / RTSP" if cam_type == "ip" else "Câmera do Dispositivo (Webcam Local)"
    
    # Teste rápido de frame
    frame, err = capture_camera_frame(cfg)
    status_conexao = "Conectada e Operacional" if frame else f"Erro ao acessar ({err})"
    
    return (
        f"Status da Câmera:\n"
        f"- Tipo: {tipo_desc}\n"
        f"- Endereço/URL: {ip_url if cam_type == 'ip' else 'Dispositivo Local (/dev/video0 ou Webcam do Navegador)'}\n"
        f"- Saudação Automática de Pessoas: {'Ativada' if auto_greet else 'Desativada'}\n"
        f"- Estado Atual: {status_conexao}"
    )

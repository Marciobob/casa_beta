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
    from api.database import (
        db_get_camera_config, db_get_all_residents, db_get_ai_config,
        db_get_user_cameras, db_get_camera_by_id_or_name
    )
except ImportError:
    from logger import vision_logger
    from database import (
        db_get_camera_config, db_get_all_residents, db_get_ai_config,
        db_get_user_cameras, db_get_camera_by_id_or_name
    )

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

import urllib.request
import urllib.parse
import urllib.error
import http.client
import socket

# =========================================================================
# MOTOR DE CAPTURA DE QUADROS (FRAME CAPTURE ENGINE)
# =========================================================================

def _extract_jpeg_from_bytes(data: bytes) -> Optional[bytes]:
    """Extrai um quadro JPEG válido delimitado por SOI (0xFFD8) e EOI (0xFFD9) ou PNG."""
    if not data or len(data) < 10:
        return None
    s = data.find(b'\xff\xd8')
    if s != -1:
        e = data.find(b'\xff\xd9', s + 2)
        if e != -1:
            return data[s:e+2]
        # Se contiver início JPEG e tamanho razoável
        if len(data) > 500:
            return data[s:]
    if data.startswith(b'\x89PNG'):
        return data
    return None


def _fetch_ip_camera_snapshot(
    raw_url: str,
    username: str = "",
    password: str = "",
    timeout: float = 3.5
) -> Tuple[Optional[bytes], Optional[str]]:
    """
    Obtém um quadro JPEG de câmeras IP com múltiplos mecanismos de resiliência:
    - Normalização automática de URLs (prefixos http://, https://, rtsp://).
    - Headers de navegador real para evitar que micro-servidores (ESP32-CAM, GoAhead, Boa, IP Webcam) rejeitem ou fechem conexões.
    - 'Connection: close' e 'Accept-Encoding: identity' para evitar 'Remote end closed connection without response'.
    - Suporte a streams MJPEG com extração do primeiro frame JPEG completo.
    - Autenticação HTTP Basic e Digest.
    - Fallback para urllib e raw socket HTTP/1.0.
    - Fallback para OpenCV (RTSP / streams H.264 / MJPEG).
    """
    url = (raw_url or "").strip()
    if not url:
        return None, "URL da Câmera IP não fornecida."

    if not (url.lower().startswith("http://") or url.lower().startswith("https://") or url.lower().startswith("rtsp://")):
        url = f"http://{url}"

    browser_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        "Accept-Encoding": "identity",
        "Connection": "close",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache"
    }

    # 1. Tentativa via socket TCP direto (suporte completo a HTTP/0.9, HTTP/1.0, HTTP/1.1 e ESP32-CAM)
    if url.lower().startswith("http://"):
        try:
            parsed = urllib.parse.urlparse(url)
            host = parsed.hostname
            port = parsed.port or 80
            path = parsed.path or "/"
            if parsed.query:
                path += f"?{parsed.query}"

            if host:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(min(4.0, timeout))
                s.connect((host, port))
                auth_header = ""
                if username and password:
                    b64_auth = base64.b64encode(f"{username}:{password}".encode("latin1")).decode("ascii")
                    auth_header = f"Authorization: Basic {b64_auth}\r\n"
                http_req = (
                    f"GET {path} HTTP/1.0\r\n"
                    f"Host: {host}\r\n"
                    f"User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/122.0.0.0\r\n"
                    f"Accept: image/*,*/*\r\n"
                    f"{auth_header}"
                    f"Connection: close\r\n\r\n"
                )
                s.sendall(http_req.encode("ascii"))
                raw_response = bytearray()
                while len(raw_response) < 3 * 1024 * 1024:
                    try:
                        chunk = s.recv(4096)
                        if not chunk:
                            break
                        raw_response.extend(chunk)
                        # Se já recebeu o frame JPEG completo (0xFFD8 ... 0xFFD9), encerra imediatamente
                        s_idx = raw_response.find(b'\xff\xd8')
                        if s_idx != -1:
                            e_idx = raw_response.find(b'\xff\xd9', s_idx + 2)
                            if e_idx != -1:
                                break
                    except socket.timeout:
                        break
                s.close()
                jpeg_candidate = _extract_jpeg_from_bytes(raw_response)
                if jpeg_candidate and len(jpeg_candidate) > 200:
                    return bytes(jpeg_candidate), None
        except Exception as e_sock:
            vision_logger.debug(f"[VisionTools] raw socket na Câmera IP ({url}) falhou: {e_sock}")

    # 2. Tentativa via requests com streaming/MJPEG e autenticação (Basic e Digest)
    if url.lower().startswith("http://") or url.lower().startswith("https://"):
        auth_methods = [None]
        if username and password:
            auth_methods = [HTTPBasicAuth(username, password), HTTPDigestAuth(username, password)]

        for auth in auth_methods:
            try:
                with requests.get(url, auth=auth, headers=browser_headers, stream=True, timeout=timeout) as resp:
                    if resp.status_code == 200:
                        content_chunks = bytearray()
                        for chunk in resp.iter_content(chunk_size=4096):
                            if chunk:
                                content_chunks.extend(chunk)
                                jpeg_candidate = _extract_jpeg_from_bytes(content_chunks)
                                if jpeg_candidate and len(jpeg_candidate) > 500 and (content_chunks.find(b'\xff\xd9', content_chunks.find(b'\xff\xd8') + 2) != -1 or len(content_chunks) > 30000):
                                    return bytes(jpeg_candidate), None
                            if len(content_chunks) > 3 * 1024 * 1024:
                                break
                        
                        if content_chunks:
                            jpeg_candidate = _extract_jpeg_from_bytes(content_chunks)
                            if jpeg_candidate and len(jpeg_candidate) > 200:
                                return bytes(jpeg_candidate), None
                    elif resp.status_code == 401 and auth is not None:
                        continue
            except Exception as e_req:
                vision_logger.debug(f"[VisionTools] requests stream na Câmera IP ({url}) falhou: {e_req}")

        # 3. Tentativa via urllib com HTTP/1.0
        try:
            req = urllib.request.Request(url, headers=browser_headers)
            if username and password:
                b64_auth = base64.b64encode(f"{username}:{password}".encode("latin1")).decode("ascii")
                req.add_header("Authorization", f"Basic {b64_auth}")

            with urllib.request.urlopen(req, timeout=timeout) as u_resp:
                raw_data = u_resp.read(3 * 1024 * 1024)
                jpeg_candidate = _extract_jpeg_from_bytes(raw_data)
                if jpeg_candidate and len(jpeg_candidate) > 200:
                    return bytes(jpeg_candidate), None
        except Exception as e_urllib:
            vision_logger.debug(f"[VisionTools] urllib na Câmera IP ({url}) falhou: {e_urllib}")

    # 4. Tentativa via OpenCV (RTSP / Streams H.264 / MJPEG)
    if cv2 is not None:
        try:
            cap_url = url
            if username and password and "://" in url and "@" not in url:
                proto, rest = url.split("://", 1)
                cap_url = f"{proto}://{urllib.parse.quote(username)}:{urllib.parse.quote(password)}@{rest}"

            cap = cv2.VideoCapture(cap_url)
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            if cap.isOpened():
                for _ in range(2):
                    cap.read()
                ret, frame = cap.read()
                cap.release()
                if ret and frame is not None:
                    success, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
                    if success:
                        return buffer.tobytes(), None
            else:
                cap.release()
        except Exception as e_cv:
            vision_logger.warning(f"[VisionTools] OpenCV da Câmera IP ({url}) falhou: {e_cv}")

    return None, f"Não foi possível obter imagem da Câmera IP no endereço '{raw_url}'."


def capture_camera_frame(
    config: Optional[Dict[str, Any]] = None,
    camera_identifier: Optional[Any] = None,
    timeout: float = 4.0
) -> Tuple[Optional[bytes], Optional[str]]:
    """
    Captura um quadro (frame JPEG) da câmera solicitada ou da câmera padrão do usuário.
    Retorna (bytes_jpeg, mensagem_erro).
    """
    cfg = config
    if not cfg:
        if camera_identifier and _ACTIVE_VISION_USER:
            cfg = db_get_camera_by_id_or_name(_ACTIVE_VISION_USER, camera_identifier)
        elif _ACTIVE_CAMERA_CONFIG:
            cfg = _ACTIVE_CAMERA_CONFIG
        elif _ACTIVE_VISION_USER:
            cfg = db_get_camera_by_id_or_name(_ACTIVE_VISION_USER, "padrao")
            
    if not cfg:
        cfg = {"camera_type": "device", "camera_device_index": 0}

    camera_type = cfg.get("camera_type", "device")

    # 1. CÂMERA IP (RTSP / HTTP SNAPSHOT / MJPEG / ESP32-CAM)
    if camera_type == "ip":
        ip_url = (cfg.get("camera_ip_url") or "").strip()
        username = (cfg.get("camera_username") or "").strip()
        password = (cfg.get("camera_password") or "").strip()
        return _fetch_ip_camera_snapshot(ip_url, username, password, timeout=timeout)

    # 2. CÂMERA DO DISPOSITIVO (WEBCAM LOCAL / BROWSER WEBCAM)
    device_index = int(cfg.get("camera_device_index", 0))
    vision_logger.info(f"Tentando capturar frame da Câmera Local (Dispositivo índice {device_index})")

    # Verifica se existem dispositivos /dev/video no Linux antes de inicializar OpenCV
    video_devices = [f"/dev/video{i}" for i in range(5) if os.path.exists(f"/dev/video{i}")]

    # Tentativa via OpenCV local
    if cv2 is not None and (video_devices or os.name == 'nt'):
        candidate_indices = [device_index]
        for alt_idx in [0, 1, 2]:
            if alt_idx not in candidate_indices and (os.path.exists(f"/dev/video{alt_idx}") or os.name == 'nt'):
                candidate_indices.append(alt_idx)

        for idx in candidate_indices:
            backends = [None]
            if hasattr(cv2, "CAP_V4L2") and os.name != 'nt':
                backends.append(cv2.CAP_V4L2)

            for backend in backends:
                try:
                    if backend is not None:
                        cap = cv2.VideoCapture(idx, backend)
                    else:
                        cap = cv2.VideoCapture(idx)

                    if cap.isOpened():
                        for _ in range(2):
                            cap.read()
                        ret, frame = cap.read()
                        cap.release()
                        if ret and frame is not None:
                            success, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
                            if success:
                                if idx != device_index:
                                    vision_logger.info(f"Câmera capturada com sucesso no índice alternativo {idx}")
                                return buffer.tobytes(), None
                    else:
                        cap.release()
                except Exception as e_dev:
                    vision_logger.debug(f"Tentativa de acesso à câmera no índice {idx} falhou: {e_dev}")

    # Fallback: snapshot enviado pelo navegador via interface web
    cached = get_latest_browser_snapshot(_ACTIVE_VISION_USER)
    if cached:
        vision_logger.info("Utilizando snapshot recebido pelo navegador do usuário.")
        return cached, None

    # Diagnóstico de permissão no Linux
    video_devices = [f"/dev/video{i}" for i in range(5) if os.path.exists(f"/dev/video{i}")]
    if video_devices:
        err_msg = (
            f"Dispositivos de vídeo encontrados ({', '.join(video_devices)}), mas sem permissão de acesso. "
            "No Linux/Kali, adicione seu usuário ao grupo de vídeo executando: 'sudo usermod -aG video $USER' "
            "e reinicie a sessão, ou verifique se a webcam não está sendo usada por outro processo."
        )
    else:
        err_msg = (
            "Nenhuma câmera local (/dev/video*) foi detectada no sistema operacional. "
            "Se você estiver usando uma Máquina Virtual (Kali Linux em VirtualBox/VMware), "
            "conecte a webcam física na VM através do menu Dispositivos > USB da sua máquina virtual."
        )

    return None, err_msg

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
def ver_camera(solicitacao: str = "Descreva detalhadamente o que você está vendo no ambiente", camera: str = "") -> str:
    """
    Acessa a câmera (webcam local ou câmera IP configurada) em tempo real, captura uma foto do ambiente
    e analisa a imagem com inteligência artificial para descrever o que está acontecendo, objetos,
    iluminação ou responder a perguntas visuais do usuário.
    
    Args:
        solicitacao: A pergunta ou foco do que deve ser analisado e descrito (ex: 'O que tem na mesa?', 'As luzes estão acesas?').
        camera: Nome ou identificador da câmera desejada (ex: 'sala', 'garagem', 'câmera 1', 'todas'). Deixe vazio para usar a câmera padrão.
    """
    vision_logger.info(f"Executando tool ver_camera com solicitação: '{solicitacao}' | Câmera: '{camera}'")
    
    cam_str = (camera or "").strip().lower()
    
    # Se o usuário solicitou olhar 'todas' as câmeras
    if cam_str in ["todas", "todas as cameras", "todas as câmeras", "all", "tudo"]:
        cams = [c for c in db_get_user_cameras(_ACTIVE_VISION_USER) if c.get("enabled", True)]
        if not cams:
            return "Nenhuma câmera cadastrada ou habilitada no sistema."
        if len(cams) == 1:
            cam_target = cams[0]
        else:
            relatorios = []
            for c in cams:
                c_name = c.get("name", "Câmera")
                f_bytes, err = capture_camera_frame(config=c)
                if not f_bytes:
                    relatorios.append(f"Câmera '{c_name}': Indisponível no momento.")
                    continue
                sys_prompt = (
                    f"Você é o sistema de visão computacional da assistente residencial Sexta-Feira. "
                    f"Você está examinando a câmera '{c_name}'. "
                    "Descreva o que está vendo de forma concisa e natural em uma ou duas frases em texto puro (sem markdown). "
                    f"Foco solicitado: {solicitacao}"
                )
                desc = analyze_image_with_vision(f_bytes, sys_prompt)
                relatorios.append(f"Câmera '{c_name}': {desc}")
            return "\n\n".join(relatorios)
    else:
        cam_target = db_get_camera_by_id_or_name(_ACTIVE_VISION_USER, camera) if camera else (_ACTIVE_CAMERA_CONFIG or db_get_camera_by_id_or_name(_ACTIVE_VISION_USER, "padrao"))

    cam_name = cam_target.get("name", "Principal") if cam_target else "Principal"
    frame_bytes, err = capture_camera_frame(config=cam_target)
    if not frame_bytes:
        return f"Aviso de Câmera ({cam_name}): {err or 'Não foi possível capturar imagem da câmera no momento.'}"
        
    system_prompt = (
        f"Você é o sistema de visão computacional da assistente residencial Sexta-Feira. "
        f"Você está visualizando a transmissão da câmera '{cam_name}'. "
        "Analise a imagem da câmera e responda em português brasileiro de forma natural, concisa e acolhedora. "
        "Evite formatação Markdown como asteriscos ou negrito para que o sintetizador de voz (TTS) fale de forma fluida. "
        f"Instrução específica do usuário: {solicitacao}"
    )
    
    return analyze_image_with_vision(frame_bytes, system_prompt)


@tool
def detectar_e_cumprimentar_pessoas(saudacao_personalizada: str = "", camera: str = "") -> str:
    """
    Verifica a câmera do ambiente para identificar a presença de pessoas.
    Se encontrar alguém, compara as características faciais com as fotos cadastradas dos moradores da casa:
    - Se for um morador cadastrado: cumprimenta a pessoa pelo nome (ex: 'Olá, Marcio! Seja bem-vindo à sua casa.') e confirma que é morador oficial.
    - Se for alguém não cadastrado / visitante: cumprimenta educadamente como visitante informando que não encontrou cadastro de morador.
    - Se o ambiente estiver vazio: informa que o cômodo está livre no momento.
    
    Args:
        saudacao_personalizada: Instrução extra de cumprimento se fornecida pelo usuário.
        camera: Nome ou identificador da câmera a ser verificada (ex: 'sala', 'garagem', 'entrada', 'todas'). Deixe vazio para a padrão.
    """
    vision_logger.info(f"Executando tool detectar_e_cumprimentar_pessoas | Câmera: '{camera}'")
    
    cam_str = (camera or "").strip().lower()
    if cam_str in ["todas", "todas as cameras", "todas as câmeras"]:
        cams = [c for c in db_get_user_cameras(_ACTIVE_VISION_USER) if c.get("enabled", True)]
        if not cams:
            return "Nenhuma câmera cadastrada no sistema."
        cam_target = cams[0]
    else:
        cam_target = db_get_camera_by_id_or_name(_ACTIVE_VISION_USER, camera) if camera else (_ACTIVE_CAMERA_CONFIG or db_get_camera_by_id_or_name(_ACTIVE_VISION_USER, "padrao"))

    cam_name = cam_target.get("name", "Principal") if cam_target else "Principal"
    frame_bytes, err = capture_camera_frame(config=cam_target)
    if not frame_bytes:
        return f"Aviso de Câmera ({cam_name}): {err or 'Não foi possível acessar a câmera para verificar a presença de pessoas.'}"
        
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
        f"Você é a assistente residencial inteligente Sexta-Feira. "
        f"A Imagem 1 fornecida é a captura ao vivo da câmera '{cam_name}' da residência. "
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
def identificar_morador_ou_visitante(detalhes_solicitados: str = "", camera: str = "") -> str:
    """
    Examina a câmera do ambiente e avalia formalmente a identidade de quem está presente,
    comparando os traços faciais com o banco de fotos dos moradores cadastrados da residência.
    Retorna se a pessoa presente é um Morador Oficial (informando o nome) ou um Visitante / Pessoa Não Cadastrada.
    
    Args:
        detalhes_solicitados: Informação ou pergunta específica sobre quem está no cômodo (ex: 'O morador Marcio está na sala?', 'Quem é a pessoa filmada?').
        camera: Nome ou identificador da câmera (ex: 'sala', 'garagem', 'entrada'). Deixe vazio para a padrão.
    """
    vision_logger.info(f"Executando tool identificar_morador_ou_visitante | Câmera: '{camera}'")
    
    cam_target = db_get_camera_by_id_or_name(_ACTIVE_VISION_USER, camera) if camera else (_ACTIVE_CAMERA_CONFIG or db_get_camera_by_id_or_name(_ACTIVE_VISION_USER, "padrao"))
    cam_name = cam_target.get("name", "Principal") if cam_target else "Principal"
    
    frame_bytes, err = capture_camera_frame(config=cam_target)
    if not frame_bytes:
        return f"Aviso de Câmera ({cam_name}): {err or 'Não foi possível acessar a câmera para avaliar a identidade das pessoas.'}"
        
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
        f"Você é o módulo de reconhecimento e segurança da assistente residencial Sexta-Feira. "
        f"A Imagem 1 é a câmera ao vivo '{cam_name}' da residência. "
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
def status_camera(camera: str = "") -> str:
    """
    Verifica e retorna o status de todas as câmeras cadastradas no sistema ou de uma câmera específica
    (se é Câmera Local ou IP/ESP32, endereço configurado, padrão do sistema e se a conexão está funcionando).
    
    Args:
        camera: Nome ou identificador de uma câmera específica (ex: 'sala', 'garagem', 'câmera 1'). Deixe vazio para ver o status de todas as câmeras.
    """
    cam_str = (camera or "").strip().lower()
    
    # Se solicitou câmera específica
    if cam_str and cam_str not in ["todas", "todas as cameras", "todas as câmeras", "all", "tudo"]:
        cam = db_get_camera_by_id_or_name(_ACTIVE_VISION_USER, camera)
        if not cam:
            return f"Câmera '{camera}' não foi encontrada nas configurações."
            
        cam_type = cam.get("camera_type", "device")
        ip_url = cam.get("camera_ip_url", "")
        tipo_desc = "Câmera IP / RTSP / ESP32" if cam_type == "ip" else "Câmera do Dispositivo (Webcam Local)"
        
        frame, err = capture_camera_frame(config=cam)
        status_conexao = "Conectada e Operacional" if frame else f"Erro ao acessar ({err})"
        
        return (
            f"Status da Câmera {cam.get('name', 'Principal')}:\n"
            f"- Tipo: {tipo_desc}\n"
            f"- Endereço/URL: {ip_url if cam_type == 'ip' else 'Dispositivo Local (/dev/video0 ou Navegador)'}\n"
            f"- Câmera Padrão: {'Sim' if cam.get('is_default') else 'Não'}\n"
            f"- Estado Atual: {status_conexao}"
        )
        
    # Listagem de todas as câmeras
    cameras = db_get_user_cameras(_ACTIVE_VISION_USER)
    if not cameras:
        return "Nenhuma câmera cadastrada no sistema."
        
    lines = [f"Status das Câmeras ({len(cameras)} configurada{'s' if len(cameras) > 1 else ''}):"]
    for idx, c in enumerate(cameras, start=1):
        f, err = capture_camera_frame(config=c)
        st = "Conectada e Operacional" if f else f"Falha de Conexão ({err or 'sem resposta'})"
        is_def = " ⭐ [Padrão]" if c.get("is_default") else ""
        c_type = "IP/RTSP" if c.get("camera_type") == "ip" else "Local"
        lines.append(f"{idx}. {c.get('name', 'Câmera')}{is_def} ({c_type}): {st}")
        
    return "\n".join(lines)

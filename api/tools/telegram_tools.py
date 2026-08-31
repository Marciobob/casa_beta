import os
from typing import Optional, Dict, Any
from langchain_core.tools import tool

try:
    from api.logger import system_logger
    from api.database import db_get_telegram_config
    from api.telegram_bot import send_telegram_message, send_telegram_photo
    from api.tools.vision_tools import capture_camera_frame
except ImportError:
    from logger import system_logger
    from database import db_get_telegram_config
    from telegram_bot import send_telegram_message, send_telegram_photo
    from tools.vision_tools import capture_camera_frame

# =========================================================================
# CONTEXTO DE EXECUÇÃO DO TELEGRAM DO USUÁRIO
# =========================================================================

_ACTIVE_TELEGRAM_USER: str = ""
_ACTIVE_TELEGRAM_TOKEN: str = ""
_ACTIVE_TELEGRAM_CHAT_ID: str = ""

def set_telegram_context(user_email: str = "", bot_token: str = "", chat_id: str = ""):
    """Configura o usuário ativo e credenciais do Telegram para execução das tools."""
    global _ACTIVE_TELEGRAM_USER, _ACTIVE_TELEGRAM_TOKEN, _ACTIVE_TELEGRAM_CHAT_ID
    _ACTIVE_TELEGRAM_USER = (user_email or "").strip().lower()
    
    if bot_token and chat_id:
        _ACTIVE_TELEGRAM_TOKEN = bot_token.strip()
        _ACTIVE_TELEGRAM_CHAT_ID = str(chat_id).strip()
    elif _ACTIVE_TELEGRAM_USER:
        cfg = db_get_telegram_config(_ACTIVE_TELEGRAM_USER)
        _ACTIVE_TELEGRAM_TOKEN = cfg.get("bot_token", "")
        _ACTIVE_TELEGRAM_CHAT_ID = cfg.get("chat_id", "")
    else:
        _ACTIVE_TELEGRAM_TOKEN = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
        _ACTIVE_TELEGRAM_CHAT_ID = (os.getenv("TELEGRAM_CHAT_ID") or "").strip()

def _get_active_credentials() -> tuple[str, str]:
    token = _ACTIVE_TELEGRAM_TOKEN
    chat_id = _ACTIVE_TELEGRAM_CHAT_ID
    if (not token or not chat_id) and _ACTIVE_TELEGRAM_USER:
        cfg = db_get_telegram_config(_ACTIVE_TELEGRAM_USER)
        token = token or cfg.get("bot_token", "")
        chat_id = chat_id or cfg.get("chat_id", "")
    if not token:
        token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    if not chat_id:
        chat_id = (os.getenv("TELEGRAM_CHAT_ID") or "").strip()
    return token, chat_id

# =========================================================================
# FERRAMENTAS LANGCHAIN DE TELEGRAM
# =========================================================================

@tool
def enviar_mensagem_telegram(mensagem: str) -> str:
    """
    Envia uma mensagem de texto, alerta ou notificação externa diretamente para o Telegram do usuário.
    Use quando o usuário pedir para você 'me mande uma mensagem no Telegram', 'notifique no Telegram',
    ou para enviar alertas remotos urgentes (ex: alerta de segurança, lembrete importante).
    
    Args:
        mensagem: O texto da mensagem a ser enviada no Telegram.
    """
    token, chat_id = _get_active_credentials()
    if not token or not chat_id:
        return "Aviso: O Telegram do usuário ainda não está configurado ou vinculado. Configure o Bot Token e Chat ID no painel de configurações."
        
    success, msg = send_telegram_message(token, chat_id, mensagem)
    if success:
        return f"Mensagem enviada com sucesso para o Telegram do usuário: '{mensagem}'"
    return f"Falha ao enviar mensagem no Telegram: {msg}"


@tool
def enviar_foto_telegram(legenda: str = "Foto capturada pela câmera da residência") -> str:
    """
    Captura a câmera do ambiente em tempo real e envia a foto com uma legenda diretamente para o Telegram do usuário.
    Use quando o usuário pedir para você enviar uma foto do cômodo, da casa ou da câmera no Telegram dele.
    
    Args:
        legenda: Texto explicativo que acompanhará a foto no Telegram.
    """
    token, chat_id = _get_active_credentials()
    if not token or not chat_id:
        return "Aviso: O Telegram do usuário não está configurado. Configure o Bot Token no painel."
        
    frame_bytes, err = capture_camera_frame()
    if not frame_bytes:
        return f"Não foi possível capturar a foto da câmera: {err or 'Sem sinal de vídeo'}"
        
    success, msg = send_telegram_photo(token, chat_id, frame_bytes, legenda)
    if success:
        return f"Foto da câmera capturada e enviada com sucesso para o Telegram com a legenda: '{legenda}'"
    return f"Falha ao enviar foto para o Telegram: {msg}"

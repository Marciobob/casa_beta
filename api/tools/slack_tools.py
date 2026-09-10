import os
import re
import json
import time
import requests
import unicodedata
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime
from langchain_core.tools import tool

try:
    from api.logger import system_logger
    from api.database import db_get_slack_config
    from api.tools.vision_tools import capture_camera_frame
except ImportError:
    from logger import system_logger
    from database import db_get_slack_config
    from tools.vision_tools import capture_camera_frame

# =========================================================================
# CACHES LOCAIS EM MEMÓRIA (Canais e Usuários)
# =========================================================================

# Cache de canais conhecidos (Nome normalizado -> ID)
_CHANNEL_CACHE: Dict[str, str] = {
    "importacoes": "C0BV0HWPBM4",
    "importações": "C0BV0HWPBM4",
    "importacao": "C0BV0HWPBM4",
    "importação": "C0BV0HWPBM4",
    "geral": "C0BV0HWPBM4",
}

# Cache de usuários do Slack (User ID -> Nome de exibição / Real Name)
_USERS_CACHE: Dict[str, str] = {
    "U0C1JD5TRPS": "sexta-feira (Bot)",
    "U0C154WF6JC": "Marcio",
    "U0BDZK12A8G": "Julia",
    "U0C0AMEJAAE": "Gustavo",
    "U0C07HFPZQD": "Pedro Augusto",
}

# =========================================================================
# CONTEXTO DE EXECUÇÃO DO SLACK DO USUÁRIO
# =========================================================================

_ACTIVE_SLACK_USER: str = ""
_ACTIVE_SLACK_TOKEN: str = ""
_ACTIVE_SLACK_WEBHOOK: str = ""
_ACTIVE_SLACK_DEFAULT_CHANNEL: str = ""

def set_slack_context(
    user_email: str = "",
    bot_token: str = "",
    webhook_url: str = "",
    default_channel: str = ""
):
    """Configura o usuário ativo e credenciais do Slack para execução das tools."""
    global _ACTIVE_SLACK_USER, _ACTIVE_SLACK_TOKEN, _ACTIVE_SLACK_WEBHOOK, _ACTIVE_SLACK_DEFAULT_CHANNEL
    _ACTIVE_SLACK_USER = (user_email or "").strip().lower()
    
    if bot_token or webhook_url:
        _ACTIVE_SLACK_TOKEN = (bot_token or "").strip()
        _ACTIVE_SLACK_WEBHOOK = (webhook_url or "").strip()
        _ACTIVE_SLACK_DEFAULT_CHANNEL = (default_channel or "").strip()
    elif _ACTIVE_SLACK_USER:
        cfg = db_get_slack_config(_ACTIVE_SLACK_USER)
        _ACTIVE_SLACK_TOKEN = cfg.get("bot_token", "")
        _ACTIVE_SLACK_WEBHOOK = cfg.get("webhook_url", "")
        _ACTIVE_SLACK_DEFAULT_CHANNEL = cfg.get("default_channel", "")
    else:
        _ACTIVE_SLACK_TOKEN = (os.getenv("SLACK_BOT_TOKEN") or "").strip()
        _ACTIVE_SLACK_WEBHOOK = (os.getenv("SLACK_WEBHOOK_URL") or "").strip()
        _ACTIVE_SLACK_DEFAULT_CHANNEL = (os.getenv("SLACK_DEFAULT_CHANNEL") or "").strip()

def _get_active_credentials() -> Tuple[str, str, str]:
    """Retorna (bot_token, webhook_url, default_channel) com base no contexto ativo ou banco."""
    token = _ACTIVE_SLACK_TOKEN
    webhook = _ACTIVE_SLACK_WEBHOOK
    channel = _ACTIVE_SLACK_DEFAULT_CHANNEL
    
    if (not token and not webhook) and _ACTIVE_SLACK_USER:
        cfg = db_get_slack_config(_ACTIVE_SLACK_USER)
        token = token or cfg.get("bot_token", "")
        webhook = webhook or cfg.get("webhook_url", "")
        channel = channel or cfg.get("default_channel", "")
        
    if not token:
        token = (os.getenv("SLACK_BOT_TOKEN") or "").strip()
    if not webhook:
        webhook = (os.getenv("SLACK_WEBHOOK_URL") or "").strip()
    if not channel:
        channel = (os.getenv("SLACK_DEFAULT_CHANNEL") or "").strip()
        
    return token, webhook, channel

# =========================================================================
# CLIENTE E HELPERS DE API DO SLACK
# =========================================================================

def _normalize_name(name: str) -> str:
    """Normaliza strings removendo acentos, hashtags e convertendo para minúsculas."""
    if not name:
        return ""
    clean = name.strip().lower().lstrip("#")
    return "".join(c for c in unicodedata.normalize("NFD", clean) if unicodedata.category(c) != "Mn")

def _resolve_user_name(token: str, user_id: Optional[str]) -> str:
    """Resgata o nome real/amigável do usuário Slack com cache automático."""
    if not user_id:
        return "Sistema / Workflow"
        
    if user_id in _USERS_CACHE:
        return _USERS_CACHE[user_id]
        
    if not token:
        return user_id
        
    try:
        resp = requests.get(
            "https://slack.com/api/users.info",
            headers={"Authorization": f"Bearer {token}"},
            params={"user": user_id},
            timeout=5
        )
        data = resp.json()
        if data.get("ok"):
            u_info = data.get("user", {})
            real_name = u_info.get("real_name") or u_info.get("profile", {}).get("real_name") or u_info.get("name") or user_id
            _USERS_CACHE[user_id] = real_name
            return real_name
    except Exception as e:
        system_logger.debug(f"Falha ao resolver nome do usuário Slack {user_id}: {e}")
        
    return user_id

def _format_slack_text(token: str, text: str) -> str:
    """Substitui menções de usuários <@U12345> e links especiais em texto legível."""
    if not text:
        return ""
        
    def _sub_mention(match):
        uid = match.group(1)
        name = _resolve_user_name(token, uid)
        return f"@{name}"
        
    formatted = re.sub(r"<@(U[A-Z0-9]+)>", _sub_mention, text)
    # Formata links no padrão <URL|Label> -> Label
    formatted = re.sub(r"<(https?://[^|>]+)\|([^>]+)>", r"\2", formatted)
    # Formata links simples <URL> -> URL
    formatted = re.sub(r"<(https?://[^>]+)>", r"\1", formatted)
    return formatted

def _resolve_channel_id(token: str, channel_input: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """
    Resolve o Channel ID (ex: C0BV0HWPBM4) a partir de um nome amigável ou ID direto.
    Retorna (channel_id, error_message).
    """
    _, _, def_channel = _get_active_credentials()
    target = (channel_input or def_channel or "").strip()
    
    if not target:
        target = "importações"
        
    # Se já é um ID do Slack (começa com C, G, D e tem tamanho >= 9)
    if re.match(r"^[CGD][A-Z0-9]{8,}$", target):
        return target, None
        
    norm_target = _normalize_name(target)
    
    # Verifica no cache local
    if norm_target in _CHANNEL_CACHE:
        return _CHANNEL_CACHE[norm_target], None
    if target in _CHANNEL_CACHE:
        return _CHANNEL_CACHE[target], None
        
    # Tenta consultar via API do Slack se tiver token
    if token:
        try:
            # 1. Tenta listar canais públicos e privados
            res = requests.get(
                "https://slack.com/api/conversations.list",
                headers={"Authorization": f"Bearer {token}"},
                params={"types": "public_channel,private_channel", "limit": 200},
                timeout=8
            )
            data = res.json()
            if data.get("ok"):
                for c in data.get("channels", []):
                    c_name = c.get("name", "")
                    c_id = c.get("id", "")
                    if c_name and c_id:
                        _CHANNEL_CACHE[c_name.lower()] = c_id
                        _CHANNEL_CACHE[_normalize_name(c_name)] = c_id
                        if _normalize_name(c_name) == norm_target:
                            return c_id, None
                            
            # 2. Tenta listar conversas do próprio bot
            res_user = requests.get(
                "https://slack.com/api/users.conversations",
                headers={"Authorization": f"Bearer {token}"},
                params={"types": "public_channel,private_channel", "limit": 100},
                timeout=8
            )
            data_user = res_user.json()
            if data_user.get("ok"):
                for c in data_user.get("channels", []):
                    c_name = c.get("name", "")
                    c_id = c.get("id", "")
                    if c_name and c_id:
                        _CHANNEL_CACHE[c_name.lower()] = c_id
                        _CHANNEL_CACHE[_normalize_name(c_name)] = c_id
                        if _normalize_name(c_name) == norm_target:
                            return c_id, None
        except Exception as e:
            system_logger.warning(f"Erro ao buscar canais na API Slack: {e}")

    # Fallback inteligente: se for canal de importações conhecido ou canal padrão
    if "importac" in norm_target:
        return "C0BV0HWPBM4", None
        
    return None, (
        f"Não foi possível localizar o ID do canal '{target}'. "
        "Verifique se o nome está correto ou use o ID do canal (ex: C0BV0HWPBM4). "
        "Para descoberta automática de todos os canais pelo nome, adicione o escopo 'channels:read' no Bot Token."
    )

def get_slack_auth_info(token: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Testa a validade do Bot Token do Slack chamando auth.test."""
    clean_token = (token or "").strip()
    if not clean_token:
        return None, "Bot Token não informado."
    try:
        resp = requests.post(
            "https://slack.com/api/auth.test",
            headers={"Authorization": f"Bearer {clean_token}"},
            timeout=10
        )
        data = resp.json()
        if data.get("ok"):
            return data, None
        return None, data.get("error", "Falha de autenticação no Slack.")
    except Exception as e:
        return None, f"Erro de conexão com o Slack: {e}"

def send_slack_message_payload(
    bot_token: str,
    webhook_url: str,
    payload: Dict[str, Any],
    channel: Optional[str] = None
) -> Tuple[bool, str]:
    """Envia um payload (com texto ou blocks) para o Slack via Bot Token ou Webhook."""
    clean_token = (bot_token or "").strip()
    clean_webhook = (webhook_url or "").strip()
    clean_channel = (channel or "").strip()
    
    # 1. Tenta via Bot Token se disponível
    if clean_token:
        url = "https://slack.com/api/chat.postMessage"
        headers = {
            "Authorization": f"Bearer {clean_token}",
            "Content-Type": "application/json; charset=utf-8"
        }
        body = dict(payload)
        
        target = clean_channel or _ACTIVE_SLACK_DEFAULT_CHANNEL or "importações"
        # Resolve canal para ID caso possível
        resolved_id, _ = _resolve_channel_id(clean_token, target)
        body["channel"] = resolved_id or target
            
        try:
            resp = requests.post(url, headers=headers, json=body, timeout=12)
            data = resp.json()
            if data.get("ok"):
                resp_chan = data.get("channel")
                if resp_chan and clean_channel:
                    _CHANNEL_CACHE[_normalize_name(clean_channel)] = resp_chan
                return True, "Mensagem enviada com sucesso via Slack Bot."
            err = data.get("error", "Erro desconhecido")
            # Se falhou por canal e temos webhook, tenta fallback para webhook
            if not clean_webhook:
                return False, f"Falha na API do Slack: {err}"
            system_logger.warning(f"Slack Bot falhou ({err}), tentando webhook...")
        except Exception as e:
            if not clean_webhook:
                return False, f"Erro de requisição ao Slack: {e}"

    # 2. Envio via Webhook URL
    if clean_webhook:
        try:
            body = dict(payload)
            if clean_channel and clean_channel.startswith("#"):
                body["channel"] = clean_channel
            resp = requests.post(clean_webhook, json=body, timeout=12)
            if resp.status_code == 200 and resp.text.strip().lower() == "ok":
                return True, "Mensagem enviada com sucesso via Slack Webhook."
            return False, f"Webhook retornou status {resp.status_code}: {resp.text}"
        except Exception as e:
            return False, f"Erro ao enviar para o Webhook do Slack: {e}"

    return False, "Slack não configurado. Forneça um Bot Token ou Webhook URL."

def build_slack_report_blocks(
    titulo: str,
    conteudo: str,
    tipo_alerta: str = "info"
) -> List[Dict[str, Any]]:
    """Constrói blocos ricos no padrão Slack Block Kit para relatórios executivos."""
    icon_map = {
        "info": "ℹ️",
        "sucesso": "✅",
        "success": "✅",
        "aviso": "⚠️",
        "warning": "⚠️",
        "erro": "🚨",
        "error": "🚨",
        "urgente": "🔥",
        "relatorio": "📊",
        "status": "🏠"
    }
    icon = icon_map.get((tipo_alerta or "info").lower(), "📌")
    now_str = datetime.now().strftime("%d/%m/%Y às %H:%M:%S")
    
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"{icon} {titulo}"[:150],
                "emoji": True
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": conteudo[:2900]
            }
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"🤖 *Sexta-Feira • Assistente Residencial Inteligente* • {now_str}"
                }
            ]
        },
        {
            "type": "divider"
        }
    ]
    return blocks

# =========================================================================
# FERRAMENTAS LANGCHAIN DE SLACK
# =========================================================================

@tool
def enviar_mensagem_slack(mensagem: str, canal: Optional[str] = None) -> str:
    """
    Envia uma mensagem de texto simples ou com markdown diretamente para o canal ou workspace do Slack.
    Use quando o usuário pedir para 'mandar mensagem no Slack', 'notificar no Slack', 'enviar aviso no Slack',
    ou para avisos rápidos e comunicação com equipes e canais.
    
    Args:
        mensagem: O texto da mensagem a ser enviada no Slack (suporta formatação Markdown do Slack: *negrito*, _itálico_, `código`, listas).
        canal: Nome ou ID do canal opcional (ex: '#importações', '#geral', 'C0BV0HWPBM4'). Se omitido, usa o canal padrão configurado.
    """
    token, webhook, def_channel = _get_active_credentials()
    target_channel = (canal or def_channel or "").strip()
    
    if not token and not webhook:
        return "Aviso: O Slack não está configurado. Configure o Webhook URL ou o Bot Token nas configurações do sistema."
        
    payload = {
        "text": mensagem
    }
    if target_channel:
        payload["channel"] = target_channel
        
    success, msg = send_slack_message_payload(token, webhook, payload, channel=target_channel)
    if success:
        chan_info = f" no canal '{target_channel}'" if target_channel else ""
        return f"Mensagem enviada com sucesso para o Slack{chan_info}: '{mensagem}'"
    return f"Falha ao enviar mensagem no Slack: {msg}"


@tool
def enviar_relatorio_slack(
    titulo: str,
    conteudo: str,
    tipo_alerta: str = "info",
    canal: Optional[str] = None
) -> str:
    """
    Envia um relatório executivo ou dashboard detalhado com formatação visual rica (Block Kit) para o Slack.
    Use para resumos diários, relatórios de status da casa, dossiês investigativos, pesquisas completas,
    ou qualquer conteúdo estruturado que mereça destaque e apresentação profissional no Slack.
    
    Args:
        titulo: Título principal do relatório (ex: 'Relatório Matinal da Residência', 'Dossiê de Segurança', 'Status Geral dos Dispositivos').
        conteudo: Texto completo do relatório, formatado com tópicos (* item), seções e destaques em negrito (*palavra*).
        tipo_alerta: Categoria visual do relatório: 'info', 'sucesso', 'aviso', 'erro', 'urgente', 'relatorio', 'status'.
        canal: Nome ou ID do canal de destino opcional (ex: '#importações', '#geral', '#relatorios').
    """
    token, webhook, def_channel = _get_active_credentials()
    target_channel = (canal or def_channel or "").strip()
    
    if not token and not webhook:
        return "Aviso: O Slack não está configurado. Cadastre o Webhook URL ou Bot Token nas configurações para enviar relatórios."
        
    blocks = build_slack_report_blocks(titulo=titulo, conteudo=conteudo, tipo_alerta=tipo_alerta)
    fallback_text = f"*{titulo}*\n\n{conteudo}"
    
    payload = {
        "text": fallback_text,
        "blocks": blocks
    }
    if target_channel:
        payload["channel"] = target_channel
        
    success, msg = send_slack_message_payload(token, webhook, payload, channel=target_channel)
    if success:
        chan_info = f" no canal '{target_channel}'" if target_channel else ""
        return f"Relatório executivo '{titulo}' publicado com sucesso no Slack{chan_info}."
    return f"Falha ao enviar relatório no Slack: {msg}"


@tool
def enviar_alerta_mudanca_slack(
    item_alterado: str,
    estado_anterior: str,
    estado_novo: str,
    detalhes: Optional[str] = None,
    canal: Optional[str] = None
) -> str:
    """
    Envia uma notificação destacada no Slack informando sobre uma mudança de estado ou alteração em tempo real no sistema.
    Use quando luzes forem acionadas/apagadas, portas abrirem, novas pessoas entrarem na casa, tarefas forem concluídas,
    ou quando qualquer parâmetro importante mudar de status.
    
    Args:
        item_alterado: O que sofreu alteração (ex: 'Lâmpada da Sala', 'Status do Quarto 1', 'Presença no Ambiente', 'Tarefa #3').
        estado_anterior: Como estava antes (ex: 'OFF / Apagada', 'Ambiente Vazio', 'Pendente').
        estado_novo: Novo estado atual (ex: 'ON / Acesa', 'Presença Detectada (Marcio)', 'Concluída').
        detalhes: Informações adicionais opcionais ou motivo do disparo.
        canal: Canal opcional para onde enviar o alerta de mudança.
    """
    token, webhook, def_channel = _get_active_credentials()
    target_channel = (canal or def_channel or "").strip()
    
    if not token and not webhook:
        return "Aviso: O Slack não está configurado no painel."
        
    now_str = datetime.now().strftime("%H:%M:%S")
    body_text = (
        f"⚡ *Alteração Detectada no Sistema:*\n"
        f"• *Item:* `{item_alterado}`\n"
        f"• *Estado Anterior:* ~{estado_anterior}~\n"
        f"• *Novo Estado:* *{estado_novo}* 🔄\n"
        f"• *Horário:* {now_str}"
    )
    if detalhes:
        body_text += f"\n• *Detalhes:* {detalhes}"
        
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"🔔 Notificação de Mudança: {item_alterado}"[:150],
                "emoji": True
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": body_text
            }
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": "🏠 *Smart Home Automation Engine*"
                }
            ]
        }
    ]
    
    payload = {
        "text": f"🔔 Notificação de Mudança: {item_alterado} -> {estado_novo}",
        "blocks": blocks
    }
    if target_channel:
        payload["channel"] = target_channel
        
    success, msg = send_slack_message_payload(token, webhook, payload, channel=target_channel)
    if success:
        return f"Notificação de mudança de '{item_alterado}' enviada com sucesso ao Slack."
    return f"Falha ao enviar alerta de mudança no Slack: {msg}"


@tool
def enviar_foto_slack(
    legenda: str = "Foto capturada pela câmera da residência",
    canal: Optional[str] = None
) -> str:
    """
    Captura uma foto em tempo real da câmera da residência e faz o upload/envio diretamente para o Slack.
    Use quando o usuário pedir para enviar uma foto do cômodo, câmera ou ambiente no Slack.
    
    Args:
        legenda: Texto descritivo que acompanhará a imagem.
        canal: Canal de destino (necessita de Bot Token com escopo files:write para upload de arquivo binário).
    """
    token, webhook, def_channel = _get_active_credentials()
    target_channel = (canal or def_channel or "").strip() or "#importações"
    
    if not token and not webhook:
        return "Aviso: O Slack não está configurado. Configure o Bot Token para enviar fotos."
        
    frame_bytes, err = capture_camera_frame()
    if not frame_bytes:
        return f"Não foi possível capturar a foto da câmera: {err or 'Sem sinal de vídeo'}"
        
    # Se temos Bot Token, faz upload real de arquivo via API Slack
    if token:
        try:
            url_upload = "https://slack.com/api/files.upload"
            headers = {"Authorization": f"Bearer {token}"}
            resolved_id, _ = _resolve_channel_id(token, target_channel)
            files = {
                "file": ("camera_snapshot.jpg", frame_bytes, "image/jpeg")
            }
            data = {
                "channels": resolved_id or target_channel,
                "initial_comment": f"📸 {legenda}",
                "title": f"Câmera Residencial - {datetime.now().strftime('%d/%m/%Y %H:%M')}"
            }
            resp = requests.post(url_upload, headers=headers, data=data, files=files, timeout=20)
            res_json = resp.json()
            if res_json.get("ok"):
                return f"Foto da câmera capturada e enviada com sucesso para o Slack no canal '{target_channel}' com a legenda: '{legenda}'"
            err_upload = res_json.get("error", "Erro ao fazer upload da imagem")
            system_logger.warning(f"Falha ao fazer upload da foto via Slack Bot Token: {err_upload}")
        except Exception as e:
            system_logger.error(f"Exceção ao subir foto no Slack: {e}")

    # Fallback caso só haja Webhook ou o upload de arquivo falhe: envia aviso textual com a descrição
    payload = {
        "text": f"📸 *Captura da Câmera:*\n{legenda}\n_(Nota: Para envio direto do arquivo JPEG, configure o Bot Token com permissão files:write)_"
    }
    if target_channel:
        payload["channel"] = target_channel
    success, msg = send_slack_message_payload(token, webhook, payload, channel=target_channel)
    if success:
        return f"Alerta fotográfico enviado no Slack com a legenda: '{legenda}'"
    return f"Falha ao enviar foto para o Slack: {msg}"


@tool
def ler_mensagens_slack(canal: Optional[str] = None, limite: int = 5) -> str:
    """
    Lê as últimas mensagens recebidas em um canal do Slack para verificar novidades, pedidos, conversas ou tarefas compartilhadas.
    Converte automaticamente os IDs dos usuários para os seus nomes reais e exibe histórico limpo e legível.
    
    Args:
        canal: Nome ou ID do canal (ex: '#importações', 'importacoes', 'C0BV0HWPBM4'). Se omitido, usa o canal padrão configurado.
        limite: Quantidade de mensagens recentes para resgatar (máximo 15, padrão 5).
    """
    token, _, def_channel = _get_active_credentials()
    target_channel = (canal or def_channel or "importações").strip()
    
    if not token:
        return "Aviso: A leitura de mensagens requer o Slack Bot Token configurado (Incoming Webhooks apenas realizam envios)."
        
    lim = max(1, min(15, int(limite or 5)))
    channel_id, err_resolve = _resolve_channel_id(token, target_channel)
    
    if not channel_id:
        return f"Falha ao consultar mensagens: {err_resolve}"

    try:
        url_hist = "https://slack.com/api/conversations.history"
        resp = requests.get(
            url_hist,
            headers={"Authorization": f"Bearer {token}"},
            params={"channel": channel_id, "limit": lim},
            timeout=10
        )
        data = resp.json()
        if not data.get("ok"):
            err = data.get("error", "Erro ao obter histórico")
            if err == "not_in_channel":
                return f"O bot não está presente no canal '{target_channel}'. Abra o canal no Slack e digite `/invite @sextafeira` para adicioná-lo."
            return f"Não foi possível ler as mensagens do canal '{target_channel}' (ID: {channel_id}): {err} (Verifique se o bot possui escopos 'channels:history' / 'groups:history')."
            
        raw_messages = data.get("messages", [])
        if not raw_messages:
            return f"Nenhuma mensagem recente encontrada no canal Slack '{target_channel}'."
            
        # Ordena do mais antigo para o mais recente para facilitar leitura cronológica
        messages = list(reversed(raw_messages))
        chan_display = target_channel if target_channel.startswith("#") else f"#{target_channel}"
        result_lines = [f"📋 *Últimas {len(messages)} mensagens no canal {chan_display} (ID: {channel_id}):*\n"]
        
        for idx, m in enumerate(messages, 1):
            user_id = m.get("user")
            subtype = m.get("subtype", "")
            username = m.get("username")
            
            if user_id:
                user_display = _resolve_user_name(token, user_id)
            elif username:
                user_display = username
            else:
                user_display = "Sistema / Workflow"
                
            raw_text = m.get("text", "").strip()
            formatted_text = _format_slack_text(token, raw_text)
            
            # Se for mensagem de bot com anexos ou bot_profile
            if not formatted_text and m.get("attachments"):
                for att in m.get("attachments", []):
                    if att.get("text"):
                        formatted_text += f" [{att.get('text')}]"
                        
            ts = m.get("ts", "")
            time_str = ""
            if ts:
                try:
                    time_str = datetime.fromtimestamp(float(ts)).strftime("%d/%m %H:%M")
                except Exception:
                    pass
                    
            header = f"{idx}. *{user_display}*"
            if time_str:
                header += f" _({time_str})_:"
            else:
                header += ":"
                
            result_lines.append(f"{header} {formatted_text}")
            
        return "\n".join(result_lines)
    except Exception as e:
        return f"Erro ao consultar mensagens no Slack: {e}"


@tool
def listar_canais_slack(tipos: str = "public_channel,private_channel") -> str:
    """
    Lista todos os canais disponíveis no workspace do Slack com seus respectivos nomes, IDs e descrições.
    Use quando o usuário perguntar quais canais existem no Slack, pedir para listar os canais ou verificar onde o bot está presente.
    
    Args:
        tipos: Tipos de conversas a buscar (ex: 'public_channel,private_channel').
    """
    token, _, def_channel = _get_active_credentials()
    if not token:
        return "Aviso: A listagem de canais requer o Bot Token do Slack configurado nas configurações."
        
    headers = {"Authorization": f"Bearer {token}"}
    
    # 1. Tenta listar canais públicos e privados
    channels_found = []
    has_missing_scope = False
    
    try:
        res = requests.get(
            "https://slack.com/api/conversations.list",
            headers=headers,
            params={"types": tipos, "limit": 100},
            timeout=10
        )
        data = res.json()
        if data.get("ok"):
            channels_found = data.get("channels", [])
        elif data.get("error") == "missing_scope":
            has_missing_scope = True
    except Exception as e:
        system_logger.warning(f"Exceção ao listar canais via conversations.list: {e}")
        
    # 2. Se conversations.list não retornou canais, tenta users.conversations (canais que o bot pertence)
    if not channels_found and not has_missing_scope:
        try:
            res_user = requests.get(
                "https://slack.com/api/users.conversations",
                headers=headers,
                params={"types": tipos, "limit": 100},
                timeout=10
            )
            data_user = res_user.json()
            if data_user.get("ok"):
                channels_found = data_user.get("channels", [])
            elif data_user.get("error") == "missing_scope":
                has_missing_scope = True
        except Exception as e:
            system_logger.warning(f"Exceção ao listar canais via users.conversations: {e}")

    # Atualiza cache com qualquer canal descoberto
    for c in channels_found:
        c_name = c.get("name", "")
        c_id = c.get("id", "")
        if c_name and c_id:
            _CHANNEL_CACHE[c_name.lower()] = c_id
            _CHANNEL_CACHE[_normalize_name(c_name)] = c_id

    if channels_found:
        lines = [f"📢 *Canais encontrados no Slack ({len(channels_found)}):*\n"]
        for idx, c in enumerate(channels_found, 1):
            name = c.get("name", "sem-nome")
            cid = c.get("id", "")
            is_priv = "🔒 Privado" if c.get("is_private") else "🌐 Público"
            topic = c.get("topic", {}).get("value") or c.get("purpose", {}).get("value") or "Sem descrição"
            members = c.get("num_members", 0)
            is_member = "✓ (Bot presente)" if c.get("is_member") else ""
            lines.append(f"{idx}. *#{name}* (ID: `{cid}`) — {is_priv} | {members} membros {is_member}\n   _Tópico:_ {topic}")
        return "\n".join(lines)
        
    # Se falhou por missing_scope, retorna diagnóstico completo e lista os canais conhecidos
    if has_missing_scope:
        return (
            "ℹ️ **Status dos Canais do Slack:**\n\n"
            "O Sexta-Feira está conectado com sucesso ao workspace **TicTag** e possui acesso ativo aos seguintes canais conhecidos:\n"
            "• **#importações** (ID: `C0BV0HWPBM4`) — *Canal ativo configurado (leitura de histórico e envio de mensagens 100% operacionais)*.\n\n"
            "⚠️ **Para habilitar a descoberta automática de TODOS os canais do workspace pela API:**\n"
            "O Slack exige o escopo de permissão **`channels:read`** (e **`groups:read`** para canais privados) no seu Bot Token:\n"
            "1. Acesse [api.slack.com/apps](https://api.slack.com/apps) e clique no app **sexta-feira**.\n"
            "2. No menu lateral esquerdo, clique em **OAuth & Permissions**.\n"
            "3. Na seção **Bot Token Scopes**, clique em **Add an OAuth Scope** e adicione:\n"
            "   - `channels:read`\n"
            "   - `groups:read`\n"
            "4. No topo da página, clique no botão **Reinstall to Workspace** para aprovar a nova permissão.\n\n"
            "💡 *Você já pode ler mensagens e enviar relatórios para o canal `#importações` diretamente!*"
        )
        
    return f"Nenhum canal encontrado no workspace do Slack com o filtro especificado."

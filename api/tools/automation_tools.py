import os
import json
from typing import Optional, Dict, Any, List
from datetime import datetime, timezone
import dateutil.tz
from langchain_core.tools import tool

try:
    from api.logger import system_logger, agent_logger
    from api.database import (
        db_get_automations,
        db_get_automation_by_id,
        db_create_automation,
        db_update_automation,
        db_delete_automation,
        db_toggle_automation
    )
    from api.video_automation import clear_video_cooldown
except ImportError:
    from logger import system_logger, agent_logger
    from database import (
        db_get_automations,
        db_get_automation_by_id,
        db_create_automation,
        db_update_automation,
        db_delete_automation,
        db_toggle_automation
    )
    from video_automation import clear_video_cooldown

# =========================================================================
# CONTEXTO DE EXECUÇÃO DO USUÁRIO
# =========================================================================

_ACTIVE_AUTOMATION_USER: str = ""

def set_automation_context(user_email: str = ""):
    """Configura o usuário ativo para as ferramentas de automação."""
    global _ACTIVE_AUTOMATION_USER
    _ACTIVE_AUTOMATION_USER = (user_email or "").strip().lower()


def _get_active_user() -> str:
    """Retorna o e-mail do usuário ativo ou fallback para variável/banco."""
    global _ACTIVE_AUTOMATION_USER
    if _ACTIVE_AUTOMATION_USER:
        return _ACTIVE_AUTOMATION_USER
    return (os.getenv("CURRENT_USER_EMAIL") or os.getenv("GMAIL_EMAIL") or "").strip().lower()


def _find_user_automation(user_email: str, identifier: str) -> Optional[Dict[str, Any]]:
    """Localiza uma automação pelo ID numérico ou por nome/termo correspondente."""
    clean_email = (user_email or "").strip().lower()
    autos = db_get_automations(clean_email)
    ident_str = str(identifier or "").strip()
    if not ident_str:
        return None

    # 1. Busca por ID numérico exato
    if ident_str.isdigit():
        target_id = int(ident_str)
        for a in autos:
            if a.get("id") == target_id:
                return a

    # 2. Busca exata por nome (ignorando maiúsculas/minúsculas)
    for a in autos:
        if a.get("name", "").strip().lower() == ident_str.lower():
            return a

    # 3. Busca por substring no nome
    for a in autos:
        if ident_str.lower() in a.get("name", "").lower() or a.get("name", "").lower() in ident_str.lower():
            return a

    # 4. Busca por tipo de automação (ex: "camera", "agenda", "resumo")
    type_map = {
        "camera": "video_face_recognition",
        "video": "video_face_recognition",
        "facial": "video_face_recognition",
        "quarto": "video_face_recognition",
        "agenda": "calendar_reminder",
        "calendario": "calendar_reminder",
        "resumo": "daily_summary",
        "matinal": "daily_summary",
        "luzes": "mqtt_schedule"
    }
    for keyword, mapped_type in type_map.items():
        if keyword in ident_str.lower():
            for a in autos:
                if a.get("automation_type") == mapped_type:
                    return a

    return None


# =========================================================================
# FERRAMENTAS LANGCHAIN DE CONTROLE DE AUTOMAÇÕES
# =========================================================================

@tool
def listar_automacoes() -> str:
    """
    Lista todas as automações e regras de segundo plano cadastradas para o usuário.
    Mostra o ID, nome, status (Ativa ✅ / Desativada ⏸️), tipo da automação, gatilho e ações configuradas.
    Use quando o usuário perguntar quais automações estão ativas, o que está agendado ou pedir para ver suas regras.
    """
    user_email = _get_active_user()
    if not user_email:
        return "Aviso: Nenhum usuário ativo identificado para consultar automações."

    automations = db_get_automations(user_email)
    if not automations:
        return "Você não possui nenhuma automação ou regra de segundo plano cadastrada no momento."

    lines = [f"Total de {len(automations)} automação(ões) cadastrada(s):\n"]
    for a in automations:
        status_icon = "✅ Ativa" if a.get("is_enabled") else "⏸️ Desativada"
        auto_type = a.get("automation_type", "")
        
        type_desc = "Tarefa"
        if auto_type == "video_face_recognition":
            type_desc = "📹 Reconhecimento Facial na Câmera"
        elif auto_type == "video_unknown_alert":
            type_desc = "🚨 Alerta de Intruso / Desconhecido"
        elif auto_type == "video_presence_detection":
            type_desc = "👥 Detecção de Presença Humana"
        elif auto_type == "calendar_reminder":
            type_desc = "⏰ Lembrete de Agenda no Telegram"
        elif auto_type == "daily_summary":
            type_desc = "☀️ Resumo Diário no Telegram"
        elif auto_type == "mqtt_schedule":
            type_desc = "💡 Agendamento de Luzes (MQTT)"
        elif auto_type == "custom_prompt":
            type_desc = "🤖 Comando do Agente"

        payload = a.get("action_payload", {}) or {}
        action_desc = ""
        if payload.get("agent_action_prompt"):
            action_desc = f" | Ação: '{payload.get('agent_action_prompt')}'"
        elif payload.get("custom_message"):
            action_desc = f" | Msg: '{payload.get('custom_message')}'"

        lines.append(
            f"• [ID {a.get('id')}] **{a.get('name')}** - {status_icon}\n"
            f"  Tipo: {type_desc} | Gatilho: {a.get('trigger_value')}{action_desc}"
        )

    return "\n".join(lines)


@tool
def controlar_automacao(identificador: str, acao: str) -> str:
    """
    Ativa ou desativa uma automação de segundo plano existente (ex: reconhecimento facial na câmera, lembrete de agenda, resumo diário).
    
    Args:
        identificador: O ID numérico da automação (ex: "69") ou o nome/termo correspondente (ex: "meu quarto", "lembrete de agenda", "resumo matinal").
        acao: 'ativar' (ou 'ligar', 'enable') para ativar a regra; 'desativar' (ou 'desligar', 'disable') para desativá-la; ou 'alternar' ('toggle').
    """
    user_email = _get_active_user()
    if not user_email:
        return "Aviso: Nenhum usuário ativo identificado para modificar automações."

    auto = _find_user_automation(user_email, identificador)
    if not auto:
        return f"Não encontrei nenhuma automação correspondente a '{identificador}'. Use 'listar_automacoes' para conferir os nomes e IDs disponíveis."

    auto_id = auto["id"]
    auto_name = auto["name"]
    clean_action = str(acao or "").strip().lower()

    if clean_action in ["ativar", "ligar", "enable", "on", "1", "true", "start"]:
        new_state = True
        status_text = "ativada com sucesso ✅"
    elif clean_action in ["desativar", "desligar", "disable", "off", "0", "false", "stop"]:
        new_state = False
        status_text = "desativada com sucesso ⏸️"
    elif clean_action in ["alternar", "toggle", "inverter"]:
        new_state = not auto.get("is_enabled", False)
        status_text = "ativada com sucesso ✅" if new_state else "desativada com sucesso ⏸️"
    else:
        return f"Ação '{acao}' não reconhecida. Especifique 'ativar' ou 'desativar'."

    updated = db_update_automation(user_email, auto_id, {"is_enabled": new_state})
    if not updated:
        return f"Erro ao atualizar o status da automação '{auto_name}' (ID {auto_id})."

    # Se foi ativada, reinicia qualquer cooldown em cache para permitir execução imediata
    if new_state:
        clear_video_cooldown(auto_id)

    agent_logger.info(f"[AutomationTools] Automação '{auto_name}' (ID {auto_id}) foi {status_text} pelo agente para {user_email}")
    return f"A automação '{auto_name}' (ID {auto_id}) foi {status_text}."


@tool
def criar_automacao(
    nome: str,
    tipo: str = "video_face_recognition",
    gatilho_valor: str = "30",
    comando_acao_residencial: Optional[str] = None,
    alvo_pessoa: str = "todos",
    mensagem_telegram: Optional[str] = None,
    cooldown_segundos: int = 300
) -> str:
    """
    Cria e registra uma nova automação de segundo plano no sistema.
    
    Args:
        nome: Nome descritivo da regra (ex: "Acender quarto ao chegar", "Resumo diário às 08:00").
        tipo: Tipo da automação:
              - 'video_face_recognition': Monitorar câmera e reconhecer morador.
              - 'video_unknown_alert': Alerta de pessoa não cadastrada/visitante.
              - 'video_presence_detection': Detecção de qualquer presença humana.
              - 'calendar_reminder': Lembrete de compromissos da Google Agenda no Telegram.
              - 'daily_summary': Resumo matinal diário de compromissos e tarefas no Telegram.
              - 'custom_prompt': Comando inteligente periódico do agente.
        gatilho_valor: O valor do gatilho:
                       - Para vídeo: segundos de intervalo entre verificações (ex: "30" ou "15").
                       - Para agenda: minutos de antecedência (ex: "15" ou "30").
                       - Para resumo diário: horário no formato HH:MM (ex: "08:00" ou "21:00").
        comando_acao_residencial: Comando em linguagem natural que a IA executará ao disparar (ex: "acender luz do quarto 1", "ligar luzes da sala e entrada").
        alvo_pessoa: Nome do morador alvo para reconhecimento ou "todos".
        mensagem_telegram: Mensagem personalizada de notificação para o Telegram.
        cooldown_segundos: Tempo em segundos entre disparos consecutivos para evitar repetições (ex: 300 para 5 min, 60 para 1 min, 0 para sem cooldown).
    """
    user_email = _get_active_user()
    if not user_email:
        return "Aviso: Nenhum usuário ativo identificado para criar automações."

    clean_tipo = tipo.strip().lower()
    trigger_type = "interval_seconds"
    action_type = "video_alert"
    payload = {}

    if "video" in clean_tipo or "facial" in clean_tipo or "camera" in clean_tipo:
        if "unknown" in clean_tipo or "intruso" in clean_tipo or "visitante" in clean_tipo:
            clean_tipo = "video_unknown_alert"
            target = "desconhecido"
        elif "presence" in clean_tipo or "presenca" in clean_tipo:
            clean_tipo = "video_presence_detection"
            target = "todos"
        else:
            clean_tipo = "video_face_recognition"
            target = alvo_pessoa or "todos"

        trigger_type = "interval_seconds"
        action_type = "video_alert"
        payload = {
            "detection_mode": clean_tipo,
            "target_person": target,
            "notify_telegram": True,
            "custom_message": mensagem_telegram or "🎉 Evento identificado na câmera da residência!",
            "agent_action_prompt": comando_acao_residencial or "",
            "cooldown_seconds": int(cooldown_segundos) if cooldown_segundos is not None else 300
        }
    elif "calendar" in clean_tipo or "agenda" in clean_tipo or "compromisso" in clean_tipo:
        clean_tipo = "calendar_reminder"
        trigger_type = "event_relative_minutes"
        action_type = "telegram_alert"
        payload = {"minutes_before": int(gatilho_valor) if str(gatilho_valor).isdigit() else 15}
    elif "summary" in clean_tipo or "resumo" in clean_tipo or "matinal" in clean_tipo:
        clean_tipo = "daily_summary"
        trigger_type = "daily_time"
        action_type = "telegram_alert"
        payload = {}
    else:
        clean_tipo = "custom_prompt"
        trigger_type = "interval_minutes"
        action_type = "agent_prompt"
        payload = {"prompt": comando_acao_residencial or nome}

    try:
        created = db_create_automation(
            user_email=user_email,
            name=nome,
            automation_type=clean_tipo,
            trigger_type=trigger_type,
            trigger_value=str(gatilho_valor).strip(),
            action_type=action_type,
            action_payload=payload,
            is_enabled=True
        )
        if created:
            clear_video_cooldown(created.get("id"))
            return f"Automação '{nome}' (ID {created.get('id')}) criada e ativada com sucesso! Gatilho: {gatilho_valor}."
        return "Falha ao salvar automação no banco de dados."
    except Exception as e:
        return f"Erro ao criar automação: {e}"


@tool
def excluir_automacao(identificador: str) -> str:
    """
    Exclui e remove permanentemente uma automação cadastrada.
    
    Args:
        identificador: O ID numérico da automação ou o nome/termo correspondente.
    """
    user_email = _get_active_user()
    if not user_email:
        return "Aviso: Nenhum usuário ativo identificado."

    auto = _find_user_automation(user_email, identificador)
    if not auto:
        return f"Não encontrei nenhuma automação correspondente a '{identificador}' para excluir."

    auto_id = auto["id"]
    auto_name = auto["name"]
    
    deleted = db_delete_automation(user_email, auto_id)
    if deleted:
        clear_video_cooldown(auto_id)
        return f"A automação '{auto_name}' (ID {auto_id}) foi excluída com sucesso."
    return f"Falha ao excluir a automação ID {auto_id}."


@tool
def executar_automacao_agora(identificador: str) -> str:
    """
    Executa e testa imediatamente uma automação cadastrada sob demanda (ex: testar reconhecimento facial ou disparo de resumo agora).
    
    Args:
        identificador: O ID numérico ou nome da automação a ser executada.
    """
    user_email = _get_active_user()
    if not user_email:
        return "Aviso: Nenhum usuário ativo identificado."

    auto = _find_user_automation(user_email, identificador)
    if not auto:
        return f"Não encontrei nenhuma automação correspondente a '{identificador}' para executar."

    try:
        try:
            from api.automation_engine import AutomationEngine
        except ImportError:
            from automation_engine import AutomationEngine

        engine = AutomationEngine(poll_interval=10)
        ok, msg = engine.execute_automation_action(auto, is_manual=True)
        if ok:
            return f"Automação '{auto['name']}' executada com sucesso: {msg}"
        return f"A automação foi acionada com resultado: {msg}"
    except Exception as e:
        return f"Erro ao executar automação: {e}"

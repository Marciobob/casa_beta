"""
Ferramentas LangChain para gerenciamento de Tarefas e Lembretes (To-Do / Google Tasks).
Permite criar, listar, buscar, concluir e excluir tarefas com sincronização opcional de lembretes no Google Calendar.
"""

import os
import re
from datetime import datetime, timedelta, date
from typing import List, Dict, Any, Optional
from langchain_core.tools import tool

try:
    from api.logger import tasks_logger
    from api.database import (
        db_create_task,
        db_get_tasks,
        db_complete_task,
        db_delete_task,
        db_search_tasks,
        db_get_tasks_count
    )
    from api.tools.calendar_tools import agendar_compromisso, connect_caldav
except ImportError:
    from logger import tasks_logger
    from database import (
        db_create_task,
        db_get_tasks,
        db_complete_task,
        db_delete_task,
        db_search_tasks,
        db_get_tasks_count
    )
    try:
        from tools.calendar_tools import agendar_compromisso, connect_caldav
    except ImportError:
        agendar_compromisso = None
        connect_caldav = None

_TASK_USER_EMAIL: Optional[str] = None


def set_task_context(user_email: str):
    """Define o e-mail do usuário ativo no contexto de execução."""
    global _TASK_USER_EMAIL
    _TASK_USER_EMAIL = user_email.strip().lower() if user_email else None


def _get_active_user_email() -> str:
    """Retorna o e-mail do usuário ativo ou fallback para o .env."""
    global _TASK_USER_EMAIL
    if _TASK_USER_EMAIL:
        return _TASK_USER_EMAIL
    env_email = os.getenv("GMAIL_EMAIL") or os.getenv("GMAIL_USER") or "usuario@smarthome.local"
    return env_email.strip().lower()


def _normalize_date_input(date_str: str) -> str:
    """Normaliza expressões de data para o formato YYYY-MM-DD."""
    if not date_str:
        return ""
    d_clean = date_str.strip().lower()
    today = datetime.now()
    
    if d_clean in ("hoje", "today"):
        return today.strftime("%Y-%m-%d")
    elif d_clean in ("amanha", "amanhã", "tomorrow"):
        return (today + timedelta(days=1)).strftime("%Y-%m-%d")
    elif d_clean in ("depois de amanha", "depois de amanhã"):
        return (today + timedelta(days=2)).strftime("%Y-%m-%d")
        
    # Match YYYY-MM-DD
    m_iso = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", d_clean)
    if m_iso:
        y, m, d = int(m_iso.group(1)), int(m_iso.group(2)), int(m_iso.group(3))
        return f"{y:04d}-{m:02d}-{d:02d}"
        
    # Match DD/MM/YYYY ou DD/MM
    m_br = re.search(r"(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?", d_clean)
    if m_br:
        d = int(m_br.group(1))
        m = int(m_br.group(2))
        y = int(m_br.group(3)) if m_br.group(3) else today.year
        if y < 100:
            y += 2000
        return f"{y:04d}-{m:02d}-{d:02d}"
        
    return date_str.strip()


def _normalize_time_input(time_str: str) -> str:
    """Normaliza horários para o formato HH:MM."""
    if not time_str:
        return ""
    t_clean = time_str.strip().lower().replace("h", ":").replace("hrs", "").replace("horas", "").strip()
    m = re.search(r"(\d{1,2})(?::(\d{1,2}))?", t_clean)
    if m:
        h = int(m.group(1))
        min_val = int(m.group(2)) if m.group(2) else 0
        return f"{h:02d}:{min_val:02d}"
    return time_str.strip()


def _format_task_item(t: Dict[str, Any]) -> str:
    """Formata uma tarefa para exibição limpa e amigável."""
    status_icon = "✅" if t.get("status") == "concluida" else "📌"
    prio = t.get("priority", "media").upper()
    
    prio_str = ""
    if prio == "ALTA":
        prio_str = " [PRIORIDADE ALTA]"
    elif prio == "BAIXA":
        prio_str = " [Prioridade Baixa]"
        
    date_str = ""
    if t.get("due_date"):
        date_str = f" | Vencimento: {t['due_date']}"
        if t.get("due_time"):
            date_str += f" às {t['due_time']}"
            
    desc_str = f" - {t['description']}" if t.get("description") else ""
    return f"{status_icon} Tarefa #{t['id']}: {t['title']}{prio_str}{date_str}{desc_str}"


# =========================================================================
# FERRAMENTAS LANGCHAIN (@tool)
# =========================================================================

@tool
def criar_tarefa(
    titulo: str,
    data_vencimento: str = "",
    horario: str = "",
    prioridade: str = "media",
    descricao: str = ""
) -> str:
    """Cria e salva uma nova tarefa ou lembrete pessoal com prazo e prioridade.
    Se data ou horário forem fornecidos, também cria um lembrete no Google Calendar.
    
    Args:
        titulo: Título ou descrição resumida da tarefa (ex: 'Pagar boleto de energia', 'Comprar ração do cachorro').
        data_vencimento: Data de vencimento (ex: 'hoje', 'amanhã', '2026-08-30', '05/09/2026') (opcional).
        horario: Horário do lembrete (ex: '14:00', '09:30', '15h') (opcional).
        prioridade: Grau de importância ('alta', 'media', 'baixa') (padrão: 'media').
        descricao: Detalhes complementares ou notas da tarefa (opcional).
    """
    user_email = _get_active_user_email()
    tasks_logger.info(f"Criando tarefa: '{titulo}' | data: '{data_vencimento}' | hora: '{horario}' | prio: '{prioridade}'")
    
    if not titulo or not titulo.strip():
        return "Erro: O título da tarefa não pode estar vazio."
        
    clean_date = _normalize_date_input(data_vencimento)
    clean_time = _normalize_time_input(horario)
    
    # Se data ou horário forem especificados, tenta sincronizar um evento na Google Agenda
    cal_event_uid = ""
    sync_msg = ""
    if clean_date and agendar_compromisso:
        try:
            hora_inicio = clean_time if clean_time else "09:00"
            res_cal = agendar_compromisso.invoke({
                "titulo": f"Lembrete / Tarefa: {titulo.strip()}",
                "data_inicio": clean_date,
                "hora_inicio": hora_inicio,
                "duracao_minutos": 30,
                "descricao": f"Tarefa: {titulo.strip()}.\n{descricao.strip()}"
            })
            if "Sucesso" in res_cal or "agendado" in res_cal:
                sync_msg = f" e sincronizado na sua Google Agenda para {clean_date}" + (f" às {clean_time}" if clean_time else "")
        except Exception as err_cal:
            tasks_logger.warning(f"Aviso ao sincronizar tarefa com Google Agenda: {err_cal}")
            
    task = db_create_task(
        user_email=user_email,
        title=titulo.strip(),
        description=descricao.strip(),
        due_date=clean_date,
        due_time=clean_time,
        priority=prioridade.strip().lower(),
        calendar_event_uid=cal_event_uid
    )
    
    detalhes = []
    if clean_date:
        detalhes.append(f"Data: {clean_date}")
    if clean_time:
        detalhes.append(f"Horário: {clean_time}")
    if prioridade and prioridade.lower() != "media":
        detalhes.append(f"Prioridade: {prioridade.upper()}")
        
    det_str = f" ({', '.join(detalhes)})" if detalhes else ""
    return f"Sucesso: A tarefa '{task['title']}' foi criada{sync_msg}!{det_str}"


@tool
def listar_tarefas(status: str = "pendente", filtro_data: str = "todas", limite: int = 15) -> str:
    """Lista as tarefas e lembretes cadastrados no sistema.
    
    Args:
        status: Filtro por status ('pendente', 'concluida' ou 'todas') (padrão: 'pendente').
        filtro_data: Filtro por data ('hoje', 'todas' ou uma data no formato 'YYYY-MM-DD') (padrão: 'todas').
        limite: Quantidade máxima de tarefas retornadas (padrão: 15).
    """
    user_email = _get_active_user_email()
    tasks_logger.info(f"Listando tarefas: status='{status}', filtro_data='{filtro_data}'")
    
    clean_date_filter = _normalize_date_input(filtro_data) if filtro_data not in ("todas", "hoje") else filtro_data
    tasks = db_get_tasks(user_email=user_email, status=status, filter_date=clean_date_filter, limit=limite)
    
    if not tasks:
        if status == "pendente":
            return "Você não tem nenhuma tarefa pendente no momento! Tudo em dia."
        return "Nenhuma tarefa encontrada para os filtros solicitados."
        
    items = [_format_task_item(t) for t in tasks]
    header = f"Você tem {len(tasks)} tarefa(s) ({status}):"
    return f"{header}\n\n" + "\n".join(items)


@tool
def concluir_tarefa(termo_ou_id: str) -> str:
    """Marca uma tarefa pendente como concluída e realizada.
    
    Args:
        termo_ou_id: ID numérico da tarefa (ex: '1', '2') ou palavra-chave do título (ex: 'boleto', 'mercado', 'ração').
    """
    user_email = _get_active_user_email()
    tasks_logger.info(f"Concluindo tarefa: '{termo_ou_id}'")
    
    if not termo_ou_id or not termo_ou_id.strip():
        return "Por favor, informe o título ou número da tarefa que deseja marcar como concluída."
        
    completed = db_complete_task(user_email, termo_ou_id.strip())
    if completed:
        return f"Parabéns! A tarefa #{completed['id']} '{completed['title']}' foi marcada como concluída."
    else:
        return f"Não encontrei nenhuma tarefa pendente com '{termo_ou_id}' para concluir."


@tool
def excluir_tarefa(termo_ou_id: str) -> str:
    """Exclui e remove uma tarefa da sua lista de afazeres.
    
    Args:
        termo_ou_id: ID numérico da tarefa (ex: '1', '2') ou palavra-chave do título (ex: 'boleto', 'ração').
    """
    user_email = _get_active_user_email()
    tasks_logger.info(f"Excluindo tarefa: '{termo_ou_id}'")
    
    if not termo_ou_id or not termo_ou_id.strip():
        return "Por favor, informe o título ou número da tarefa que deseja excluir."
        
    deleted = db_delete_task(user_email, termo_ou_id.strip())
    if deleted:
        return f"Sucesso: A tarefa #{deleted['id']} '{deleted['title']}' foi excluída da sua lista."
    else:
        return f"Não encontrei nenhuma tarefa com '{termo_ou_id}' para excluir."


@tool
def buscar_tarefas(termo: str) -> str:
    """Pesquisa tarefas por palavras-chave no título ou descrição.
    
    Args:
        termo: Termo de busca (ex: 'mercado', 'pagar', 'médico', 'carro').
    """
    user_email = _get_active_user_email()
    tasks_logger.info(f"Buscando tarefas pelo termo: '{termo}'")
    
    if not termo or not termo.strip():
        return "Por favor, informe a palavra-chave para buscar as tarefas."
        
    results = db_search_tasks(user_email, termo.strip())
    if not results:
        return f"Nenhuma tarefa encontrada com o termo '{termo}'."
        
    items = [_format_task_item(t) for t in results]
    return f"Encontrei {len(results)} tarefa(s) para '{termo}':\n\n" + "\n".join(items)

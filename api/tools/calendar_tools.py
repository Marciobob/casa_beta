import os
import re
from datetime import datetime, timedelta, date, time
from typing import Optional, List, Dict, Any, Tuple
import dateutil.tz

try:
    import caldav
except ImportError:
    caldav = None

try:
    from langchain_core.tools import tool
except ImportError:
    try:
        from langchain.tools import tool
    except ImportError:
        def tool(func):
            func.name = func.__name__
            func.invoke = lambda args: func(**(args if isinstance(args, dict) else {"termo": str(args)}))
            return func

try:
    from api.logger import calendar_logger
except ImportError:
    try:
        from logger import calendar_logger
    except ImportError:
        import logging
        calendar_logger = logging.getLogger("CALENDAR")

# =========================================================================
# CONFIGURAÇÃO E CONEXÃO COM O GOOGLE CALENDAR (CalDAV)
# =========================================================================

_ACTIVE_CALENDAR_USER: Optional[str] = None
_ACTIVE_CALENDAR_PWD: Optional[str] = None

def set_calendar_credentials_context(email_user: Optional[str], app_password: Optional[str]):
    """Define as credenciais do Google Calendar para a execução do usuário ativo."""
    global _ACTIVE_CALENDAR_USER, _ACTIVE_CALENDAR_PWD
    _ACTIVE_CALENDAR_USER = (email_user or "").strip() if email_user else None
    _ACTIVE_CALENDAR_PWD = (app_password or "").replace(" ", "").strip() if app_password else None

def get_calendar_credentials() -> Tuple[Optional[str], Optional[str]]:
    """Recupera e sanitiza as credenciais do Google para o usuário ativo ou a partir do .env."""
    global _ACTIVE_CALENDAR_USER, _ACTIVE_CALENDAR_PWD
    if _ACTIVE_CALENDAR_USER and _ACTIVE_CALENDAR_PWD:
        return _ACTIVE_CALENDAR_USER, _ACTIVE_CALENDAR_PWD
        
    email_user = os.getenv("GMAIL_EMAIL") or os.getenv("GMAIL_USER")
    app_password = os.getenv("GMAIL_APP_PASSWORD") or os.getenv("GMAIL_PASSWORD")
    
    if email_user:
        email_user = email_user.strip()
    if app_password:
        app_password = app_password.replace(" ", "").strip()
        
    return email_user, app_password

def connect_caldav() -> Tuple[Optional[Any], Optional[str]]:
    """Cria e retorna o cliente CalDAV e o calendário principal do Google Agenda."""
    if caldav is None:
        err = "Biblioteca 'caldav' não está instalada no ambiente Python."
        calendar_logger.error(err)
        return None, err

    user, password = get_calendar_credentials()
    if not user or not password:
        err = (
            "Credenciais do Google Calendar não configuradas. Configure as variáveis GMAIL_EMAIL "
            "e GMAIL_APP_PASSWORD (senha de aplicativo de 16 dígitos) no arquivo .env."
        )
        calendar_logger.warning(err)
        return None, err

    url = f"https://calendar.google.com/calendar/dav/{user}/user"
    try:
        client = caldav.DAVClient(url=url, username=user, password=password)
        principal = client.principal()
        calendars = principal.calendars()
        
        if not calendars:
            return None, "Nenhum calendário encontrado na conta do Google."
            
        # Prioriza o calendário com o e-mail do usuário ou o primeiro da lista
        primary_cal = calendars[0]
        for c in calendars:
            try:
                disp_name = c.get_display_name() if hasattr(c, "get_display_name") else getattr(c, "name", "")
                if user.lower() in str(disp_name).lower():
                    primary_cal = c
                    break
            except Exception:
                pass
                
        return primary_cal, None
    except Exception as e:
        err = f"Falha na conexão com o Google Agenda via CalDAV: {e}"
        calendar_logger.error(err)
        return None, err

# =========================================================================
# UTILITÁRIOS DE PARSE E FORMATAÇÃO DE DATA / HORA
# =========================================================================

def parse_data_relativa(texto_data: str) -> date:
    """Converte termos como 'hoje', 'amanhã', 'depois de amanhã' ou '2026-08-29' para objeto date."""
    hoje = datetime.now().date()
    t = texto_data.strip().lower() if texto_data else "hoje"
    
    if t in ["hoje", "today"]:
        return hoje
    elif t in ["amanhã", "amanha", "tomorrow"]:
        return hoje + timedelta(days=1)
    elif t in ["depois de amanhã", "depois de amanha"]:
        return hoje + timedelta(days=2)
        
    # Tenta formato DD/MM/YYYY ou DD/MM
    m_br = re.match(r'^(\d{1,2})[/.-](\d{1,2})(?:[/.-](\d{2,4}))?$', t)
    if m_br:
        dia = int(m_br.group(1))
        mes = int(m_br.group(2))
        ano = int(m_br.group(3)) if m_br.group(3) else hoje.year
        if ano < 100:
            ano += 2000
        return date(ano, mes, dia)
        
    # Tenta formato ISO YYYY-MM-DD
    m_iso = re.match(r'^(\d{4})[-/](\d{1,2})[-/](\d{1,2})$', t)
    if m_iso:
        return date(int(m_iso.group(1)), int(m_iso.group(2)), int(m_iso.group(3)))
        
    return hoje

def parse_hora(texto_hora: str) -> time:
    """Converte strings de hora como '14:30', '14h30', '15h', '9', '09:00' para objeto time."""
    if not texto_hora:
        return time(9, 0) # Padrão: 09:00
        
    t = texto_hora.strip().lower()
    # Formato 14h30 ou 14h
    m_h = re.match(r'^(\d{1,2})(?:h|:)?(\d{1,2})?$', t)
    if m_h:
        hora = int(m_h.group(1))
        minuto = int(m_h.group(2)) if m_h.group(2) else 0
        return time(min(hora, 23), min(minuto, 59))
        
    return time(9, 0)

def formatar_evento(event_obj: Any) -> Dict[str, Any]:
    """Extrai informações amigáveis de um evento VEVENT do CalDAV usando icalendar."""
    summary = "(Sem Título)"
    dtstart = None
    dtend = None
    location = ""
    description = ""
    uid = ""

    comp = getattr(event_obj, "icalendar_component", None)
    if comp:
        summary_val = comp.get("summary")
        if summary_val:
            summary = str(summary_val)
            
        dtstart_val = comp.get("dtstart")
        if dtstart_val and hasattr(dtstart_val, "dt"):
            dtstart = dtstart_val.dt
            
        dtend_val = comp.get("dtend")
        if dtend_val and hasattr(dtend_val, "dt"):
            dtend = dtend_val.dt
            
        location_val = comp.get("location")
        if location_val:
            location = str(location_val)
            
        description_val = comp.get("description")
        if description_val:
            description = str(description_val)
            
        uid_val = comp.get("uid")
        if uid_val:
            uid = str(uid_val)
    else:
        # Fallback para parsing em string iCal
        raw = getattr(event_obj, "data", "") or str(event_obj)
        m_sum = re.search(r'SUMMARY:(.*)', raw)
        if m_sum:
            summary = m_sum.group(1).strip()
        m_loc = re.search(r'LOCATION:(.*)', raw)
        if m_loc:
            location = m_loc.group(1).strip()
        m_uid = re.search(r'UID:(.*)', raw)
        if m_uid:
            uid = m_uid.group(1).strip()

    # Formata início e fim em texto legível para o assistente
    str_inicio = ""
    if isinstance(dtstart, datetime):
        # Converte para fuso horário local se necessário
        try:
            tz_local = dateutil.tz.tzlocal()
            dtstart_local = dtstart.astimezone(tz_local) if dtstart.tzinfo else dtstart
            str_inicio = dtstart_local.strftime("%d/%m/%Y às %H:%M")
        except Exception:
            str_inicio = dtstart.strftime("%d/%m/%Y às %H:%M")
    elif isinstance(dtstart, date):
        str_inicio = dtstart.strftime("%d/%m/%Y (Dia Inteiro)")
    elif dtstart:
        str_inicio = str(dtstart)
        
    str_fim = ""
    if isinstance(dtend, datetime):
        try:
            tz_local = dateutil.tz.tzlocal()
            dtend_local = dtend.astimezone(tz_local) if dtend.tzinfo else dtend
            str_fim = dtend_local.strftime("%H:%M")
        except Exception:
            str_fim = dtend.strftime("%H:%M")
    elif dtend:
        str_fim = str(dtend)
        
    return {
        "uid": uid,
        "titulo": summary,
        "inicio": str_inicio,
        "fim": str_fim,
        "local": location,
        "descricao": description,
        "raw_dtstart": dtstart
    }

# =========================================================================
# FERRAMENTAS DO AGENTE LANGCHAIN (CALENDAR TOOLS)
# =========================================================================

@tool
def listar_compromissos(dias_a_frente: int = 7, data_especifica: Optional[str] = None) -> str:
    """
    Lista os compromissos e eventos agendados no Google Calendar / Agenda.
    Permite consultar a agenda de hoje, de amanhã, de uma data específica ou dos próximos N dias.
    
    Args:
        dias_a_frente: Quantidade de dias a partir de hoje a consultar (padrão: 7).
        data_especifica: Termo de data opcional como 'hoje', 'amanhã', '29/08/2026' ou '2026-08-29' para consultar apenas esse dia.
    """
    calendar_logger.info(f"Executando listar_compromissos: dias={dias_a_frente}, data_especifica='{data_especifica}'")
    cal, err = connect_caldav()
    if err or not cal:
        return err

    try:
        tz_local = dateutil.tz.tzlocal()
        agora = datetime.now(tz_local)
        
        if data_especifica:
            d_alvo = parse_data_relativa(data_especifica)
            start_dt = datetime.combine(d_alvo, time(0, 0, 0), tzinfo=tz_local)
            end_dt = datetime.combine(d_alvo, time(23, 59, 59), tzinfo=tz_local)
            rotulo_periodo = f"para o dia {d_alvo.strftime('%d/%m/%Y')}"
        else:
            start_dt = agora - timedelta(hours=1) # Inclui eventos que começaram há pouco
            end_dt = agora + timedelta(days=dias_a_frente)
            rotulo_periodo = f"para os próximos {dias_a_frente} dias"

        events = cal.search(start=start_dt, end=end_dt, expand=True)
        
        if not events:
            return f"Nenhum compromisso encontrado na sua agenda {rotulo_periodo}."
            
        formatados = []
        for e in events:
            info = formatar_evento(e)
            linha = f"• {info['titulo']} - {info['inicio']}"
            if info['fim'] and ":" in info['fim']:
                linha += f" até {info['fim']}"
            if info['local']:
                linha += f" (Local: {info['local']})"
            if info['descricao']:
                linha += f" [Notas: {info['descricao']}]"
            formatados.append(linha)
            
        calendar_logger.info(f"{len(formatados)} compromissos encontrados {rotulo_periodo}.")
        return f"Compromissos na sua agenda {rotulo_periodo} ({len(formatados)} evento(s)):\n\n" + "\n".join(formatados)
        
    except Exception as e:
        calendar_logger.error(f"Erro ao listar compromissos: {e}")
        return f"Erro ao consultar a agenda no Google Calendar: {str(e)}"

@tool
def agendar_compromisso(
    titulo: str, 
    data_inicio: str, 
    hora_inicio: str, 
    duracao_minutos: int = 60, 
    descricao: Optional[str] = "", 
    localizacao: Optional[str] = ""
) -> str:
    """
    Agenda um novo evento/compromisso no Google Calendar.
    
    Args:
        titulo: Título ou resumo do compromisso (ex: 'Consulta Médica', 'Reunião de Trabalho').
        data_inicio: Data do evento (ex: 'hoje', 'amanhã', '29/08/2026', '2026-08-30').
        hora_inicio: Horário de início (ex: '14:00', '14h30', '15h', '09:00').
        duracao_minutos: Duração estimada em minutos (padrão: 60 minutos).
        descricao: Descrição ou observações adicionais sobre o compromisso.
        localizacao: Endereço ou local onde será o compromisso (opcional).
    """
    if not titulo:
        return "Por favor, informe o título do compromisso a ser agendado."
        
    calendar_logger.info(
        f"Agendando compromisso: '{titulo}' na data '{data_inicio}' às '{hora_inicio}' "
        f"(duração={duracao_minutos}min, local='{localizacao}')"
    )
    
    cal, err = connect_caldav()
    if err or not cal:
        return err

    try:
        tz_local = dateutil.tz.tzlocal()
        d = parse_data_relativa(data_inicio)
        h = parse_hora(hora_inicio)
        
        dt_inicio = datetime.combine(d, h, tzinfo=tz_local)
        dt_fim = dt_inicio + timedelta(minutes=max(duracao_minutos, 15))
        
        # Salva o evento via CalDAV no Google Calendar
        event = cal.save_event(
            dtstart=dt_inicio,
            dtend=dt_fim,
            summary=titulo.strip(),
            description=(descricao or "").strip(),
            location=(localizacao or "").strip()
        )
        
        data_str = dt_inicio.strftime("%d/%m/%Y")
        hora_inicio_str = dt_inicio.strftime("%H:%M")
        hora_fim_str = dt_fim.strftime("%H:%M")
        
        res = f"Sucesso: O compromisso '{titulo}' foi agendado para o dia {data_str} das {hora_inicio_str} às {hora_fim_str}."
        if localizacao:
            res += f" Local: {localizacao}."
            
        calendar_logger.info(f"Compromisso agendado com sucesso: {res}")
        return res
    except Exception as e:
        calendar_logger.error(f"Erro ao agendar compromisso: {e}")
        return f"Erro ao criar compromisso no Google Calendar: {str(e)}"

@tool
def buscar_compromissos(termo_busca: str) -> str:
    """
    Pesquisa compromissos na agenda pelo título, nome ou palavra-chave.
    
    Args:
        termo_busca: Palavra ou título a ser pesquisado (ex: 'dentista', 'reunião', 'academia').
    """
    if not termo_busca:
        return "Informe o que deseja buscar na agenda."
        
    calendar_logger.info(f"Buscando compromissos com termo: '{termo_busca}'")
    cal, err = connect_caldav()
    if err or not cal:
        return err

    try:
        tz_local = dateutil.tz.tzlocal()
        agora = datetime.now(tz_local)
        # Busca em um horizonte amplo de 60 dias
        start_dt = agora - timedelta(days=7)
        end_dt = agora + timedelta(days=60)
        
        events = cal.search(start=start_dt, end=end_dt, expand=True)
        encontrados = []
        
        termo_lower = termo_busca.strip().lower()
        for e in events:
            info = formatar_evento(e)
            if (termo_lower in info["titulo"].lower() or 
                termo_lower in info["descricao"].lower() or 
                termo_lower in info["local"].lower()):
                linha = f"• {info['titulo']} - {info['inicio']}"
                if info['fim'] and ":" in info['fim']:
                    linha += f" até {info['fim']}"
                if info['local']:
                    linha += f" (Local: {info['local']})"
                encontrados.append(linha)
                
        if not encontrados:
            return f"Nenhum compromisso encontrado na agenda com o termo '{termo_busca}'."
            
        return f"Encontrei {len(encontrados)} compromisso(s) relacionado(s) a '{termo_busca}':\n\n" + "\n".join(encontrados)
    except Exception as e:
        calendar_logger.error(f"Erro ao buscar compromissos: {e}")
        return f"Erro ao buscar compromissos no Google Calendar: {str(e)}"

@tool
def cancelar_compromisso(id_ou_titulo_evento: str) -> str:
    """
    Cancela e remove um compromisso da agenda do Google Calendar pelo título ou palavra-chave.
    
    Args:
        id_ou_titulo_evento: Título ou palavra-chave do evento a ser cancelado (ex: 'Consulta', 'Reunião').
    """
    if not id_ou_titulo_evento:
        return "Informe o título do compromisso que deseja cancelar."
        
    calendar_logger.info(f"Cancelando compromisso: '{id_ou_titulo_evento}'")
    cal, err = connect_caldav()
    if err or not cal:
        return err

    try:
        tz_local = dateutil.tz.tzlocal()
        agora = datetime.now(tz_local)
        start_dt = agora - timedelta(days=1)
        end_dt = agora + timedelta(days=60)
        
        events = cal.search(start=start_dt, end=end_dt, expand=True)
        termo_lower = id_ou_titulo_evento.strip().lower()
        
        target_event = None
        target_info = None
        
        for e in events:
            info = formatar_evento(e)
            if termo_lower in info["titulo"].lower() or (info["uid"] and termo_lower in info["uid"].lower()):
                target_event = e
                target_info = info
                break
                
        if not target_event:
            return f"Não encontrei nenhum compromisso com o título '{id_ou_titulo_evento}' para cancelar."
            
        # Deleta o evento
        target_event.delete()
        
        calendar_logger.info(f"Evento '{target_info['titulo']}' cancelado e removido com sucesso.")
        return f"Sucesso: O compromisso '{target_info['titulo']}' ({target_info['inicio']}) foi cancelado e removido da sua agenda."
    except Exception as e:
        calendar_logger.error(f"Erro ao cancelar compromisso: {e}")
        return f"Erro ao cancelar compromisso no Google Calendar: {str(e)}"

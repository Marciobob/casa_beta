import os
import sys
import time
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
import re
# Garante que o Python encontre os módulos independentemente do diretório de onde o comando for executado
current_dir = Path(__file__).parent.resolve()
project_root = current_dir.parent.resolve()
for path in (str(current_dir), str(project_root)):
    if path not in sys.path:
        sys.path.insert(0, path)

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage, AIMessage

# Importação dos LLMs com fallbacks
try:
    from langchain_google_genai import ChatGoogleGenerativeAI
except ImportError:
    ChatGoogleGenerativeAI = None

try:
    from langchain_openai import ChatOpenAI
except ImportError:
    ChatOpenAI = None

try:
    from api.logger import agent_logger
    from api.tools.search_tools import pesquisar_na_internet
    from api.tools.mqtt_tools import controlar_luzes, relatorio_status_casa, set_execution_context, get_executed_actions
    from api.tools.profile_tools import consultar_perfil_usuario, set_profile_context
    from api.tools.gmail_tools import ler_emails_recentes, buscar_emails, enviar_email, responder_email, apagar_email, apagar_todos_emails, set_gmail_credentials_context
    from api.tools.calendar_tools import listar_compromissos, agendar_compromisso, buscar_compromissos, cancelar_compromisso, set_calendar_credentials_context
    from api.tools.contact_tools import buscar_contato, salvar_contato, listar_contatos, excluir_contato, set_contact_credentials_context
    from api.tools.task_tools import criar_tarefa, listar_tarefas, concluir_tarefa, excluir_tarefa, buscar_tarefas, set_task_context
    from api.tools.keep_tools import (
        criar_nota, adicionar_itens_lista, marcar_item_lista, ler_nota, 
        listar_notas, excluir_nota, buscar_notas, set_keep_context
    )
    from api.tools.vision_tools import ver_camera, detectar_e_cumprimentar_pessoas, identificar_morador_ou_visitante, status_camera, set_vision_context
    from api.tools.telegram_tools import enviar_mensagem_telegram, enviar_foto_telegram, set_telegram_context
    from api.tools.slack_tools import (
        enviar_mensagem_slack,
        enviar_relatorio_slack,
        enviar_alerta_mudanca_slack,
        enviar_foto_slack,
        ler_mensagens_slack,
        listar_canais_slack,
        set_slack_context
    )
    from api.tools.automation_tools import (
        listar_automacoes,
        controlar_automacao,
        criar_automacao,
        excluir_automacao,
        executar_automacao_agora,
        set_automation_context
    )
    from api.tools.manual_tools import consultar_manual_sistema
    from api.tools.youtube_tools import pesquisar_e_transcrever_youtube
    from api.tools.music_tools import tocar_musica, parar_musica, status_musica
    from api.tools.system_tools import controlar_volume_sistema, controlar_brilho_tela, abrir_navegador_sistema, fechar_navegador_sistema, set_system_tools_context
    from api.tools.antigravity_tools import (
        consultar_agente_antigravity,
        executar_comando_antigravity,
        perguntar_e_executar_antigravity,
        set_antigravity_context
    )
    from api.tools.osint_tools import (
        investigar_pessoa_osint,
        buscar_usuario_redes_sociais_sherlock,
        verificar_email_osint_holehe,
        set_osint_context
    )
    from api.tools.memory_tools import (
        gravar_memoria_longo_prazo,
        consultar_memorias_longo_prazo,
        listar_todas_memorias,
        esquecer_memoria,
        set_memory_context,
        trigger_background_continuous_learning
    )
    from api.tools.interface_tools import (
        navegar_para_tela,
        abrir_modal,
        fechar_modal,
        alternar_aba_interface
    )
    from api.database import db_get_google_credentials, db_get_camera_config, db_get_recent_important_memories_summary, db_get_ai_config
except ImportError:
    from logger import agent_logger
    from tools.search_tools import pesquisar_na_internet
    from tools.mqtt_tools import controlar_luzes, relatorio_status_casa, set_execution_context, get_executed_actions
    from tools.profile_tools import consultar_perfil_usuario, set_profile_context
    from tools.gmail_tools import ler_emails_recentes, buscar_emails, enviar_email, responder_email, apagar_email, set_gmail_credentials_context
    from tools.calendar_tools import listar_compromissos, agendar_compromisso, buscar_compromissos, cancelar_compromisso, set_calendar_credentials_context
    from tools.contact_tools import buscar_contato, salvar_contato, listar_contatos, excluir_contato, set_contact_credentials_context
    from tools.task_tools import criar_tarefa, listar_tarefas, concluir_tarefa, excluir_tarefa, buscar_tarefas, set_task_context
    from tools.keep_tools import (
        criar_nota, adicionar_itens_lista, marcar_item_lista, ler_nota, 
        listar_notas, excluir_nota, buscar_notas, set_keep_context
    )
    from tools.vision_tools import ver_camera, detectar_e_cumprimentar_pessoas, identificar_morador_ou_visitante, status_camera, set_vision_context
    from tools.telegram_tools import enviar_mensagem_telegram, enviar_foto_telegram, set_telegram_context
    from tools.slack_tools import (
        enviar_mensagem_slack,
        enviar_relatorio_slack,
        enviar_alerta_mudanca_slack,
        enviar_foto_slack,
        ler_mensagens_slack,
        listar_canais_slack,
        set_slack_context
    )
    from tools.automation_tools import (
        listar_automacoes,
        controlar_automacao,
        criar_automacao,
        excluir_automacao,
        executar_automacao_agora,
        set_automation_context
    )
    from tools.manual_tools import consultar_manual_sistema
    from tools.youtube_tools import pesquisar_e_transcrever_youtube
    from tools.music_tools import tocar_musica, parar_musica, status_musica
    from tools.system_tools import controlar_volume_sistema, controlar_brilho_tela, abrir_navegador_sistema, fechar_navegador_sistema, set_system_tools_context
    from tools.antigravity_tools import (
        consultar_agente_antigravity,
        executar_comando_antigravity,
        perguntar_e_executar_antigravity,
        set_antigravity_context
    )
    from tools.osint_tools import (
        investigar_pessoa_osint,
        buscar_usuario_redes_sociais_sherlock,
        verificar_email_osint_holehe,
        set_osint_context
    )
    from tools.memory_tools import (
        gravar_memoria_longo_prazo,
        consultar_memorias_longo_prazo,
        listar_todas_memorias,
        esquecer_memoria,
        set_memory_context,
        trigger_background_continuous_learning
    )
    from tools.interface_tools import (
        navegar_para_tela,
        abrir_modal,
        fechar_modal,
        alternar_aba_interface
    )
    from database import db_get_google_credentials, db_get_camera_config, db_get_recent_important_memories_summary, db_get_ai_config

def get_fallback_models(primary_model: str) -> List[str]:
    """Retorna lista de modelos de fallback ordenados por preferência caso o modelo primário sofra 503/429 ou sobrecarga."""
    primary = (primary_model or "gemini-2.5-flash-lite").strip()
    primary_lower = primary.lower()
    
    if "gemini" in primary_lower:
        candidates = [primary]
        for alt in ["gemini-2.5-flash-lite", "gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]:
            if alt not in candidates:
                candidates.append(alt)
        return candidates
    else:
        candidates = [primary]
        for alt in ["gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo"]:
            if alt not in candidates:
                candidates.append(alt)
        return candidates

def get_chat_model(model_name: str, api_key: str):
    """Instancia o modelo adequado de acordo com o provedor (Google Gemini ou OpenAI)."""
    model_lower = (model_name or "gemini-2.5-flash-lite").lower()
    
    if "gemini" in model_lower:
        if ChatGoogleGenerativeAI is None:
            raise ImportError("Pacote langchain-google-genai não está instalado.")
        return ChatGoogleGenerativeAI(
            model=model_name or "gemini-2.5-flash-lite",
            google_api_key=api_key,
            temperature=0.1
        )
    else:
        if ChatOpenAI is None:
            raise ImportError("Pacote langchain-openai não está instalado.")
        return ChatOpenAI(
            model=model_name or "gpt-4o-mini",
            api_key=api_key,
            temperature=0.1
        )

def gerar_texto_para_fala(texto: str, max_chars: int = 420) -> str:
    """
    Transforma qualquer texto (com Markdown, links, tabelas e termos técnicos) em um
    texto falado limpo, natural, fluido e sem poluição, perfeito para sintetizadores de voz (TTS).
    Remove URLs completas, preposições vazias de links, símbolos Markdown e emojis.
    """
    if not texto:
        return ""
    
    # 1. Remove blocos de código completos ```...```
    t = re.sub(r'```[\s\S]*?```', '', texto)
    
    # 2. Transforma links markdown [Texto Legível](URL) apenas no Texto Legível
    t = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', t)
    
    # 3. Remove cabeçalhos markdown (#, ##, ###)
    t = re.sub(r'^#{1,6}\s+', '', t, flags=re.MULTILINE)
    
    # 4. Remove negrito, itálico, tachado e código inline
    t = re.sub(r'\*\*([^*]+)\*\*', r'\1', t)
    t = re.sub(r'\*([^*]+)\*', r'\1', t)
    t = re.sub(r'__([^_]+)__', r'\1', t)
    t = re.sub(r'_([^_]+)_', r'\1', t)
    t = re.sub(r'`([^`]+)`', r'\1', t)
    t = re.sub(r'~~([^~]+)~~', r'\1', t)
    
    # 5. Remove marcadores de lista (*, -, +, •, 1.) no início de linhas
    t = re.sub(r'^\s*[-*+•]\s+', '', t, flags=re.MULTILINE)
    t = re.sub(r'^\s*\d+\.\s+', '', t, flags=re.MULTILINE)
    
    # 6. Remove citações (> texto) e divisores (---, ***)
    t = re.sub(r'^\s*>\s+', '', t, flags=re.MULTILINE)
    t = re.sub(r'^\s*[-*_]{3,}\s*$', '', t, flags=re.MULTILINE)
    
    # 7. Remove URLs puras e expressões que as introduzem diretamente
    t = re.sub(r'(?i)(?:\b(?:com mais detalhes em|mais detalhes em|disponível em|acesse em|veja em|no link|pelo link|no site|no endereço)\s*)?https?:\/\/\S+', '', t)
    t = re.sub(r'(?i)(?:\b(?:com mais detalhes em|mais detalhes em|disponível em|acesse em|veja em|no link|pelo link|no site|no endereço)\s*)?www\.\S+', '', t)
    
    # 8. Remove rótulos soltos de link no final da linha ou antes de pontuação (ex: "Link:", "URL:", "Fonte:")
    t = re.sub(r'(?i)\b(?:links?|urls?|fontes?|acesse em|disponível em|veja em|no link|pelo link)\s*:\s*$', '', t, flags=re.MULTILINE)
    t = re.sub(r'(?i)\b(?:links?|urls?|fontes?|acesse em|disponível em|veja em|no link|pelo link)\s*:\s*', '', t)
    t = re.sub(r'(?i)\b(?:com mais detalhes em|mais detalhes em|acesse em|disponível em|veja em|no link|pelo link|no endereço|no site|no perfil)\s*(?=[.,;!?]|$)', '', t)
    
    # 9. Remove colchetes de referências numéricas [1], [2]
    t = re.sub(r'\[\d+\]', '', t)
    
    # 10. Remove emojis
    t = re.sub(r'[\U00010000-\U0010ffff]', '', t)
    
    # 11. Converte quebras de linha em pausas suaves com ponto
    linhas = [l.strip() for l in t.split('\n') if l.strip()]
    reconstruido = []
    for l in linhas:
        if not re.search(r'[.!?:]$', l):
            l += '.'
        reconstruido.append(l)
    t = " ".join(reconstruido)
    
    # 12. Limpa pontuações repetidas e múltiplos espaços
    t = re.sub(r'\s*([,.:;?!])\s*', r'\1 ', t)
    t = re.sub(r':\s*\.', '.', t)
    t = re.sub(r'\.\s*\.', '.', t)
    t = re.sub(r',\s*\.', '.', t)
    t = re.sub(r'\s+', ' ', t).strip()
    
    # 13. Se for excessivamente longo para síntese de voz (ex: relatórios OSINT extensos)
    if len(t) > max_chars:
        frases = re.split(r'(?<=[.!?])\s+', t)
        resumo = []
        acc = 0
        for f in frases:
            if acc + len(f) <= max_chars:
                resumo.append(f)
                acc += len(f)
            else:
                break
        if not resumo and frases:
            resumo.append(frases[0][:max_chars].rsplit(' ', 1)[0] + '...')
        t = " ".join(resumo).strip()
        if not t.endswith('.'):
            t += '.'
        t += " Os detalhes completos e links estão disponíveis na tela do chat."
        
    return t

def remover_markdown(texto: str) -> str:
    """Função legada para compatibilidade retroativa."""
    return gerar_texto_para_fala(texto)

def get_tool_friendly_status(tool_name: str) -> str:
    """Retorna uma mensagem amigável em português sobre a ferramenta que o agente está executando."""
    status_map = {
        "pesquisar_na_internet": "Pesquisando informações atualizadas na internet...",
        "controlar_luzes": "Enviando comando para os dispositivos da residência...",
        "relatorio_status_casa": "Verificando o status dos cômodos da casa...",
        "consultar_perfil_usuario": "Consultando seu perfil e preferências...",
        "buscar_contato": "Buscando contato na sua agenda...",
        "salvar_contato": "Salvando contato na sua agenda...",
        "listar_contatos": "Listando seus contatos...",
        "excluir_contato": "Removendo contato...",
        "criar_tarefa": "Criando tarefa no Google Tarefas...",
        "listar_tarefas": "Consultando suas tarefas pendentes...",
        "concluir_tarefa": "Concluindo tarefa...",
        "excluir_tarefa": "Removendo tarefa...",
        "buscar_tarefas": "Buscando tarefas...",
        "criar_nota": "Criando nota no Google Keep...",
        "adicionar_itens_lista": "Adicionando itens à sua lista...",
        "marcar_item_lista": "Atualizando itens da lista...",
        "ler_nota": "Lendo nota do Google Keep...",
        "listar_notas": "Consultando suas notas e listas...",
        "excluir_nota": "Removendo nota...",
        "buscar_notas": "Pesquisando suas notas...",
        "ver_camera": "Acessando e analisando a câmera...",
        "detectar_e_cumprimentar_pessoas": "Identificando pessoas na câmera...",
        "identificar_morador_ou_visitante": "Verificando morador ou visitante...",
        "status_camera": "Verificando status da câmera...",
        "enviar_mensagem_telegram": "Enviando mensagem no Telegram...",
        "enviar_foto_telegram": "Enviando foto no Telegram...",
        "enviar_mensagem_slack": "Enviando mensagem para o Slack...",
        "enviar_relatorio_slack": "Formatando e publicando relatório executivo no Slack...",
        "enviar_alerta_mudanca_slack": "Enviando alerta de alteração de estado para o Slack...",
        "enviar_foto_slack": "Capturando e enviando foto da residência para o Slack...",
        "ler_mensagens_slack": "Consultando mensagens recentes no canal do Slack...",
        "listar_canais_slack": "Consultando lista de canais disponíveis no Slack...",
        "listar_automacoes": "Consultando regras de automação...",
        "controlar_automacao": "Atualizando regra de automação...",
        "criar_automacao": "Criando nova automação...",
        "excluir_automacao": "Removendo automação...",
        "executar_automacao_agora": "Executando automação...",
        "consultar_manual_sistema": "Consultando o manual do sistema...",
        "ler_emails_recentes": "Lendo e-mails recentes no Gmail...",
        "buscar_emails": "Buscando e-mails no Gmail...",
        "enviar_email": "Enviando e-mail pelo Gmail...",
        "responder_email": "Respondendo e-mail...",
        "apagar_email": "Movendo e-mail para a lixeira...",
        "listar_compromissos": "Consultando sua agenda no Google Calendar...",
        "agendar_compromisso": "Agendando compromisso no Google Calendar...",
        "buscar_compromissos": "Buscando compromissos na agenda...",
        "cancelar_compromisso": "Cancelando compromisso na agenda...",
        "pesquisar_e_transcrever_youtube": "Pesquisando e transcrevendo tutorial no YouTube...",
        "tocar_musica": "Buscando e iniciando a reprodução da música...",
        "parar_musica": "Parando a reprodução de áudio...",
        "status_musica": "Verificando o áudio em reprodução...",
        "controlar_volume_sistema": "Ajustando o volume do computador...",
        "controlar_brilho_tela": "Ajustando o brilho da tela...",
        "abrir_navegador_sistema": "Abrindo o navegador de internet...",
        "fechar_navegador_sistema": "Fechando página do navegador...",
        "gravar_memoria_longo_prazo": "Memorizando fato importante para o futuro...",
        "consultar_memorias_longo_prazo": "Consultando memórias de longo prazo...",
        "listar_todas_memorias": "Buscando todas as memórias consolidadas...",
        "esquecer_memoria": "Removendo memória do banco de dados...",
        "consultar_agente_antigravity": "Consultando o agente especialista Antigravity...",
        "executar_comando_antigravity": "Executando comando na máquina física via Antigravity...",
        "perguntar_e_executar_antigravity": "Delegando análise e execução ao Antigravity...",
        "investigar_pessoa_osint": "Realizando investigação OSINT completa e sintetizando dossiê com o Antigravity...",
        "buscar_usuario_redes_sociais_sherlock": "Rastreando perfis nas redes sociais com Sherlock...",
        "verificar_email_osint_holehe": "Verificando contas vinculadas ao e-mail com Holehe...",
        "navegar_para_tela": "Navegando para a tela solicitada...",
        "abrir_modal": "Abrindo janela na interface do usuário...",
        "fechar_modal": "Fechando janela/modal da interface...",
        "alternar_aba_interface": "Alternando aba na interface..."
    }
    return status_map.get(tool_name, "Processando solicitação com ferramentas...")

def processar_comando_agente(
    pergunta: Optional[str] = None,
    api_key: str = "",
    modelo: str = "gemini-2.5-flash-lite",
    agent_name: str = "Sexta-Feira",
    rooms: Optional[List[Dict[str, Any]]] = None,
    rooms_state: Optional[Dict[str, bool]] = None,
    broker_config: Optional[Dict[str, Any]] = None,
    user_email: Optional[str] = None,
    user_profile: Optional[Dict[str, Any]] = None,
    chat_history: Optional[List[Dict[str, Any]]] = None,
    user_message: Optional[str] = None,
    status_callback: Optional[Any] = None,
    **kwargs
) -> Dict[str, Any]:
    """
    Executa o agente inteligente LangChain com histórico conversacional,
    integração com Gmail, Google Calendar, pesquisa, controle de luzes, relatórios, perfil e memória de longo prazo.
    """
    prompt_text = (pergunta if pergunta is not None else user_message) or ""
    status_cb = status_callback or kwargs.get("status_callback")
    if not broker_config and ("broker" in kwargs or "port" in kwargs):
        broker_config = {"broker": kwargs.get("broker", "test.mosquitto.org"), "port": kwargs.get("port", 1883)}
        
    if not api_key and user_email:
        ai_cfg = db_get_ai_config(user_email)
        api_key = (ai_cfg.get("api_key") or "").strip()
        if not modelo or modelo == "gemini-2.5-flash-lite":
            modelo = ai_cfg.get("ai_model", modelo) or modelo
        if not agent_name or agent_name == "Sexta-Feira":
            agent_name = ai_cfg.get("agent_name", agent_name) or agent_name
            
    history_count = len(chat_history) if chat_history else 0
    agent_logger.info(
        f"Comando recebido: '{prompt_text}' | Modelo: '{modelo}' | Agente: '{agent_name}' | "
        f"Usuário: '{user_email}' | Mensagens no Histórico: {history_count}"
    )
    
    # Configura o contexto das ferramentas MQTT, Perfil, Tarefas, Notas, Visão, Telegram, Automações, Sistema, Memória e Credenciais Google
    set_execution_context(rooms_state or {}, broker_config or {})
    set_profile_context(user_email=user_email or "", profile_data=user_profile)
    set_task_context(user_email=user_email or "")
    set_keep_context(user_email=user_email or "")
    set_vision_context(user_email=user_email or "", api_key=api_key or "", model_name=modelo or "")
    set_telegram_context(user_email=user_email or "")
    set_slack_context(user_email=user_email or "")
    set_automation_context(user_email=user_email or "")
    set_system_tools_context(user_email=user_email or "")
    set_antigravity_context(user_email=user_email or "", api_key=api_key or "", model_name=modelo or "")
    set_osint_context(user_email=user_email or "", api_key=api_key or "", model_name=modelo or "")
    set_memory_context(user_email=user_email or "")
    
    # Carrega credenciais do Google do usuário ativo
    gmail_user, gmail_pwd = db_get_google_credentials(user_email or "")
    set_gmail_credentials_context(gmail_user, gmail_pwd)
    set_calendar_credentials_context(gmail_user, gmail_pwd)
    set_contact_credentials_context(gmail_user, gmail_pwd)
    
    # Carrega resumo de memórias de longo prazo aprendidas sobre o usuário
    memories_summary = db_get_recent_important_memories_summary(user_email or "", limit=10)

    # Contexto temporal em tempo real (data, hora, dia da semana e fuso)
    now_dt = datetime.now().astimezone()
    dias_semana = ["Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira", "Sexta-feira", "Sábado", "Domingo"]
    meses_ano = ["Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"]
    
    dia_semana_str = dias_semana[now_dt.weekday()]
    mes_str = meses_ano[now_dt.month - 1]
    data_formatada = f"{dia_semana_str}, {now_dt.day:02d} de {mes_str} de {now_dt.year}"
    hora_formatada = now_dt.strftime("%H:%M:%S")
    fuso_str = now_dt.strftime("%Z (UTC%z)")

    tools = [
        consultar_memorias_longo_prazo,
        listar_todas_memorias,
        esquecer_memoria,
        consultar_agente_antigravity,
        executar_comando_antigravity,
        perguntar_e_executar_antigravity,
        investigar_pessoa_osint,
        buscar_usuario_redes_sociais_sherlock,
        verificar_email_osint_holehe,
        pesquisar_na_internet,
        pesquisar_e_transcrever_youtube,
        controlar_luzes,
        relatorio_status_casa,
        consultar_perfil_usuario,
        buscar_contato,
        salvar_contato,
        listar_contatos,
        excluir_contato,
        criar_tarefa,
        listar_tarefas,
        concluir_tarefa,
        excluir_tarefa,
        buscar_tarefas,
        criar_nota,
        adicionar_itens_lista,
        marcar_item_lista,
        ler_nota,
        listar_notas,
        excluir_nota,
        buscar_notas,
        ver_camera,
        detectar_e_cumprimentar_pessoas,
        identificar_morador_ou_visitante,
        status_camera,
        enviar_mensagem_telegram,
        enviar_foto_telegram,
        enviar_mensagem_slack,
        enviar_relatorio_slack,
        enviar_alerta_mudanca_slack,
        enviar_foto_slack,
        ler_mensagens_slack,
        listar_canais_slack,
        listar_automacoes,
        controlar_automacao,
        criar_automacao,
        excluir_automacao,
        executar_automacao_agora,
        consultar_manual_sistema,
        ler_emails_recentes,
        buscar_emails,
        enviar_email,
        responder_email,
        apagar_email,
        listar_compromissos,
        agendar_compromisso,
        buscar_compromissos,
        cancelar_compromisso,
        tocar_musica,
        parar_musica,
        status_musica,
        controlar_volume_sistema,
        controlar_brilho_tela,
        abrir_navegador_sistema,
        fechar_navegador_sistema,
        navegar_para_tela,
        abrir_modal,
        fechar_modal,
        alternar_aba_interface
    ]
    tool_map = {t.name: t for t in tools}
    
    system_prompt = f"""Você é o assistente inteligente residencial, pessoal e de informações gerais chamado "{agent_name}".

CONTEXTO TEMPORAL ATUAL EM TEMPO REAL:
- Data e Dia da Semana: {data_formatada}
- Horário Atual do Sistema: {hora_formatada} ({fuso_str})
- Use SEMPRE essa data e horário exatos como referência temporal absoluta para interpretar 'hoje', 'amanhã', 'ontem', 'nesta semana', agendamento de compromissos, tarefas, buscas de e-mails, previsões do tempo e saudações conforme o turno ('bom dia', 'boa tarde', 'boa noite').

FATOS E PREFERÊNCIAS DE LONGO PRAZO QUE VOCÊ JÁ APRENDEU SOBRE O USUÁRIO:
{memories_summary}

Suas capacidades e ferramentas disponíveis:
1. MEMÓRIA DE LONGO PRAZO & APRENDIZADO AUTÔNOMO:
   - O sistema possui um motor autônomo e contínuo de aprendizado em segundo plano. Ele analisa cada conversa em background e grava automaticamente todas as preferências, gostos, rotinas, hábitos, detalhes pessoais e instruções passadas pelo usuário, sem necessidade de ferramentas síncronas de gravação durante a conversa.
   - 'consultar_memorias_longo_prazo': Use para pesquisar fatos específicos nas memórias gravadas quando o usuário fizer perguntas sobre o que você sabe ou quando precisar resgatar um detalhe passado que não esteja no resumo acima.
   - 'listar_todas_memorias': Use quando o usuário perguntar o que você lembra sobre ele, quais informações tem salvas ou o que sabe a respeito dele no total.
   - 'esquecer_memoria': Use quando o usuário pedir para você esquecer ou apagar uma informação previamente memorizada informando o ID.
2. GOOGLE KEEP, NOTAS & LISTAS DE COMPRAS:
   - 'criar_nota': Use para criar novas anotações de texto livre (ideias, lembretes rápidos) ou listas de compras/afazeres com itens.
   - 'adicionar_itens_lista': Use quando o usuário pedir para colocar/adicionar produtos ou itens em uma lista de compras existente (ex: "Adicione café e queijo na lista de compras").
   - 'marcar_item_lista': Use quando o usuário disser que comprou ou pegou um item da lista (ex: "Já comprei o leite").
   - 'ler_nota': Use sempre que o usuário perguntar o que tem na lista de compras ou pedir para ler uma nota.
   - 'listar_notas': Use para listar todas as notas e listas salvas no sistema.
   - 'excluir_nota': Use para apagar uma nota ou lista de compras.
   - 'buscar_notas': Use para pesquisar notas e listas por termo ou palavra-chave.
3. GOOGLE TAREFAS & LEMBRETES (TO-DO):
   - 'criar_tarefa': Use para criar novas tarefas, afazeres ou lembretes com data/prazo, horário e prioridade (alta/média/baixa).
   - 'listar_tarefas': Use quando o usuário perguntar quais são suas tarefas pendentes, o que tem para fazer hoje, afazeres atrasados ou concluídos.
   - 'concluir_tarefa': Use quando o usuário disser que concluiu, fez, pagou ou terminou uma tarefa.
   - 'excluir_tarefa': Use quando o usuário pedir para cancelar ou remover uma tarefa da lista.
   - 'buscar_tarefas': Use para pesquisar tarefas específicas por termo ou palavra-chave.
4. GOOGLE CONTATOS & AGENDA DE PESSOAS:
   - 'buscar_contato': Use para pesquisar telefones, e-mails ou anotações de contatos salvos no Google por nome, termo ou telefone. Se o usuário pedir para mandar um e-mail para alguém pelo nome (ex: "Envie um e-mail para o Pedro"), use 'buscar_contato' primeiro para obter o endereço de e-mail do destinatário.
   - 'salvar_contato': Use para cadastrar e salvar um novo contato na agenda do Google com nome, telefone, e-mail e notas.
   - 'listar_contatos': Use para listar os contatos salvos na agenda do usuário.
   - 'excluir_contato': Use para remover e excluir um contato da agenda do Google.
5. GOOGLE AGENDA & CALENDAR:
   - 'listar_compromissos': Use sempre que o usuário perguntar sobre sua agenda, eventos de hoje, de amanhã, compromissos da semana ou de um dia específico.
   - 'agendar_compromisso': Use para marcar/agendar novas tarefas, consultas ou compromissos na agenda do Google Calendar com data e hora.
   - 'buscar_compromissos': Use para pesquisar eventos específicos na agenda por palavra-chave ou título.
   - 'cancelar_compromisso': Use quando o usuário pedir para desmarcar, remover ou cancelar um compromisso da agenda.
6. GMAIL & E-MAILS:
   - 'ler_emails_recentes': Use para verificar sua caixa de entrada, ler novos e-mails não lidos ou ver as últimas mensagens recebidas.
   - 'buscar_emails': Use para procurar e-mails específicos por remetente, assunto ou palavra-chave.
   - 'enviar_email': Use quando o usuário pedir para enviar uma nova mensagem de e-mail para um destinatário. Se você só tiver o nome da pessoa, use 'buscar_contato' para achar o e-mail dela.
   - 'responder_email': Use para responder a um e-mail recebido (mantendo o assunto com Re: e o destinatário correto).
   - 'apagar_email': Use quando o usuário pedir expressamente para apagar ou mover um e-mail para a lixeira.
7. VISÃO COMPUTACIONAL, CÂMERA & RECONHECIMENTO DE MORADORES:
   - 'ver_camera': Use sempre que o usuário pedir para você olhar a câmera, ver o que está no ambiente, o que tem na mesa, descrever o cômodo ou responder a uma pergunta visual. Aceita o parâmetro 'camera' (ex: 'sala', 'garagem', 'câmera 1', 'todas') para inspecionar uma câmera específica ou todas as câmeras cadastradas. Deixe vazio para a câmera padrão.
   - 'detectar_e_cumprimentar_pessoas': Use quando o usuário perguntar se tem alguém na sala/ambiente, quem está no ambiente ou pedir para identificar e cumprimentar quem chegou. Aceita o parâmetro 'camera'. Compara a pessoa filmada com as fotos dos moradores cadastrados.
   - 'identificar_morador_ou_visitante': Use especificamente quando o usuário perguntar se a pessoa na câmera é um morador oficial da casa ou um visitante, ou perguntar quem está no cômodo. Aceita o parâmetro 'camera'.
   - 'status_camera': Use quando o usuário perguntar se as câmeras estão funcionando, quais câmeras estão configuradas ou o estado de uma câmera específica. Aceita o parâmetro 'camera'.
8. TELEGRAM & NOTIFICAÇÕES EXTERNAS:
   - 'enviar_mensagem_telegram': Use quando o usuário pedir para enviar um aviso, mensagem ou notificação externa para o Telegram dele (ex: "Me envie uma mensagem no Telegram avisando disso").
   - 'enviar_foto_telegram': Use quando o usuário pedir para capturar a câmera e enviar a foto diretamente no Telegram dele.
9. SLACK & INTEGRAÇÃO DE WORKSPACE (RELATÓRIOS, MUDANÇAS & CANAIS):
   - 'enviar_mensagem_slack': Use quando o usuário pedir para enviar um aviso, mensagem de texto ou notificação para o Slack ou canal específico (ex: "Mande uma mensagem no Slack", "Avise a equipe no Slack", "Mande no canal #geral").
   - 'enviar_relatorio_slack': Use SEMPRE que o usuário pedir para você trazer/enviar relatórios, resumos executivos, status da casa, pesquisas ou análises no Slack (ex: "Traga um relatório no Slack", "Me envie um relatório do status da casa no Slack", "Envie o resumo do dia no Slack"). Esta ferramenta gera cartões elegantes no Block Kit com badges de status ('info', 'sucesso', 'aviso', 'erro', 'urgente', 'relatorio', 'status') e rodapé temporal.
   - 'enviar_alerta_mudanca_slack': Use SEMPRE que você detectar ou for instruído a avisar sobre alterações de estado no sistema (ex: mudança de luzes acesas/apagadas, portas, presença detectada, alteração de automações ou tarefas concluídas).
   - 'enviar_foto_slack': Use quando o usuário pedir para capturar a câmera e postar a foto em um canal do Slack.
   - 'ler_mensagens_slack': Use quando o usuário perguntar o que foi falado no Slack, quais as últimas mensagens de um canal ou novidades compartilhadas na equipe (ex: "O que falaram no canal importações?", "Leia as mensagens do Slack").
   - 'listar_canais_slack': Use quando o usuário perguntar quais canais existem no Slack, pedir para listar os canais ou verificar quais canais estão disponíveis no workspace.
10. CONTROLE DE AUTOMAÇÕES E SEGUNDO PLANO:
   - 'listar_automacoes': Use quando o usuário perguntar quais automações estão ativas, o que está agendado, pedir para ver suas regras de segundo plano, regras de câmera/vídeo, monitor do Slack, lembretes ou resumos.
   - 'controlar_automacao': Use para ativar ('ativar') ou desativar ('desativar') uma regra de automação existente pelo nome ou ID (ex: "Desative a automação do quarto", "Ative a regra de reconhecimento facial", "Desligue o lembrete de reuniões", "Desative o monitor do Slack").
   - 'criar_automacao': Use para criar novas regras de automação periódicas, de vídeo/câmera, lembretes de agenda, resumos diários ou monitoramento do Slack. Sempre que o usuário pedir para monitorar mensagens no Slack (ex: no canal '#importações' ou outro canal), verificar pela câmera se ele está na frente do computador, falar com ele por voz se estiver presente, exibir notificação toast na tela e avisar no Telegram, crie uma automação com tipo='slack_message_monitor', canal_slack='#importações' (ou canal indicado), verificar_camera=True, falar_voz=True, notificar_tela=True, notificar_telegram=True.
   - 'excluir_automacao': Use para apagar/excluir permanentemente uma regra de automação.
   - 'executar_automacao_agora': Use para testar ou executar uma automação sob demanda imediatamente.
10. MANUAL E GUIA DE AJUDA DO SISTEMA:
   - 'consultar_manual_sistema': Use sempre que o usuário perguntar como funciona o sistema, como configurar o Telegram (@BotFather), como gerar senha de app do Google, como funciona o reconhecimento facial, como funcionam as automações, luzes MQTT, vozes ou tiver dúvidas sobre as ferramentas e telas da casa inteligente.
11. MEMÓRIA & PERFIL DO USUÁRIO: Use a ferramenta 'consultar_perfil_usuario' sempre que o usuário perguntar sobre seus dados pessoais, tipo sanguíneo, comidas preferidas, filmes/séries favoritos, músicas que gosta, carro, passeios ou notas de sua vida, ou quando você puder dar uma resposta ou recomendação personalizada baseada no perfil dele.
12. HISTÓRICO DE CONVERSA: Você tem acesso ao histórico recente das últimas mensagens trocadas nesta conversa. Use esse contexto anterior para compreender referências, pronomes (ex: "ela", "disso", "o mesmo compromisso", "o mesmo e-mail", "o mesmo cômodo") e manter continuidade no diálogo.
13. AUTOMAÇÃO RESIDENCIAL: Use a ferramenta 'controlar_luzes' para ligar ('ON') ou desligar ('OFF') as luzes dos cômodos solicitados.
    Cômodos cadastrados na residência: {rooms or []}
14. RELATÓRIO DA CASA: Use a ferramenta 'relatorio_status_casa' quando o usuário perguntar quais luzes estão acesas, o que está ligado ou o status geral da residência.
15. PESQUISA NA INTERNET: Use a ferramenta 'pesquisar_na_internet' para buscar em tempo real notícias do dia, previsão do tempo/clima, sugestões de filmes, receitas, curiosidades e fatos atualizados.
16. YOUTUBE, TUTORIAIS EM VÍDEO & TRANSCRIÇÕES: Use a ferramenta 'pesquisar_e_transcrever_youtube' sempre que o usuário pedir tutoriais passo a passo de como fazer, consertar, cozinhar ou arrumar algo do dia a dia (ex: 'como arrumar panela de pressão', 'tutorial de como consertar chuveiro', 'como trocar torneira', 'receita no youtube', 'tutorial de como fazer...'), ou quando pedir para buscar vídeos no YouTube ou transcrever/resumir um link de vídeo do YouTube. A ferramenta extrai as falas reais do vídeo para que você explique e ensine detalhadamente o passo a passo com clareza para o usuário.
17. MÚSICA, PODCASTS & REPRODUÇÃO DE ÁUDIO NO SISTEMA:
   - 'tocar_musica': Use SEMPRE que o usuário pedir para tocar, ouvir ou escutar músicas, bandas, artistas, gêneros musicais (ex: 'quero escutar um samba', 'toca Gusttavo Lima', 'coloque um pagode', 'toca Evidências', 'toca rock clássico'), podcasts (ex: 'coloque o podcast do Flow', 'toca o podcast Podpah') ou pedir para tocar um vídeo/música do YouTube nos alto-falantes da casa. A ferramenta busca e já inicia a reprodução do áudio imediatamente em segundo plano.
   - 'parar_musica': Use SEMPRE que o usuário pedir para parar, encerrar, interromper, pausar ou desligar a música ou áudio que está tocando (ex: 'para a música', 'pare a música', 'desliga o som', 'para o áudio', 'silêncio', 'chega de música').
   - 'status_musica': Use quando o usuário perguntar o que está tocando no momento ou qual música está em execução.
18. COMANDOS DA MÁQUINA FÍSICA & SISTEMA OPERACIONAL:
   - 'controlar_volume_sistema': Use SEMPRE que o usuário pedir para aumentar o volume, abaixar o volume, definir um volume em porcentagem (ex: 'coloca o volume em 50%', 'volume no máximo'), mutar ou desmutar o som do computador/máquina.
   - 'controlar_brilho_tela': Use SEMPRE que o usuário pedir para aumentar o brilho da tela, abaixar o brilho da tela ou definir um nível percentual de brilho (ex: 'aumenta o brilho da tela', 'abaixa o brilho', 'brilho em 80%').
   - 'abrir_navegador_sistema': Use SEMPRE que o usuário pedir para abrir o navegador de internet, abrir um site no navegador ou realizar uma pesquisa web diretamente no navegador do computador (ex: 'abre o navegador', 'abre o YouTube no navegador', 'pesquisa receitas no navegador').
   - 'fechar_navegador_sistema': Use SEMPRE que o usuário pedir para fechar uma página, aba ou janela do navegador aberta pelo assistente (ex: 'fecha a página', 'fecha o YouTube', 'fecha o Google', 'fecha o navegador'). Por segurança, esta ferramenta NUNCA fecha a página principal da casa inteligente / assistente.
19. INTEGRAÇÃO COM AGENTE ANTIGRAVITY (CONSULTORIA TÉCNICA & COMANDOS NO TERMINAL):
   - 'consultar_agente_antigravity': Use SEMPRE que você tiver alguma dúvida técnica, complexa, de programação, arquitetura de software, infraestrutura, engenharia ou quando o usuário pedir para perguntar/consultar o Antigravity (ex: 'pergunta pro Antigravity', 'o que o Antigravity acha disso?', 'tira uma dúvida com o Antigravity', 'qual a melhor solução técnica para isso?'). O Antigravity atua como seu engenheiro consultor sênior.
   - 'executar_comando_antigravity': Use SEMPRE que o usuário pedir para executar comandos de terminal/shell na máquina física / computador (ex: 'execute o comando df -h', 'veja o uptime do servidor', 'liste os arquivos da pasta', 'execute o comando ... na máquina'). Retorna a saída real do terminal (stdout/stderr) e o código de saída do Linux.
   - 'perguntar_e_executar_antigravity': Use quando o usuário pedir para delegar uma tarefa completa de diagnóstico ou resolução técnica no computador ao Antigravity.
20. INTELIGÊNCIA OSINT (OPEN SOURCE INTELLIGENCE) & FERRAMENTAS KALI LINUX:
   - 'investigar_pessoa_osint': Use SEMPRE que o usuário pedir para investigar uma pessoa, buscar dados de alguém, levantar informações sobre um perfil ou @ do Instagram (ex: 'investiga o @fulano', 'pesquise sobre o Marcio Silva no Instagram @marciobob', 'faça um levantamento OSINT sobre tal pessoa', 'veja tudo o que tem na internet sobre fulano'). Ela aciona ferramentas como Sherlock, Holehe, busca web direcionada e sintetiza um dossiê analítico completo através do Antigravity.
   - 'buscar_usuario_redes_sociais_sherlock': Use quando o objetivo for especificamente rastrear e listar em quais redes sociais ou plataformas um username/@ possui perfil ativo usando o Sherlock do Kali Linux.
   - 'verificar_email_osint_holehe': Use quando o objetivo for especificamente verificar em quais serviços e plataformas da internet um e-mail possui conta cadastrada usando o Holehe.
21. CONTROLE TOTAL & NAVEGAÇÃO AUTÔNOMA DA INTERFACE VISUAL (TELAS, ABAS & MODAIS):
    - 'navegar_para_tela': Use SEMPRE que o usuário pedir para mudar de tela, ir para outro dashboard ou abrir uma página do sistema:
      * 'dashboard_principal' (ou '/', 'agente', 'chat', 'inicio', 'painel principal') -> Direciona para o Painel Principal do Agente
      * 'dashboard_casa' (ou '/casa.html', 'casa', 'smart home', 'cômodos', 'luzes') -> Direciona para o Dashboard da Casa Inteligente
      * 'avatar' (ou '/avatar.html', 'assistente visual', 'tela do avatar', 'avatar 2d', 'live avatar') -> Direciona para a Tela do Avatar 2D em Tempo Real
      * 'configuracoes' (ou '/config/config.html', 'config', 'ajustes', 'broker') -> Direciona para a tela de Configurações da Casa
      * 'perfil' (ou '/profile.html', 'meu perfil', 'morador', 'dados') -> Direciona para a tela de Perfil do Usuário
      Exemplos: "Vá para o avatar", "Abra a tela do avatar", "Vá para o dashboard da casa", "Mude para a tela da casa", "Vá para o dashboard principal", "Volte para o início", "Abra as configurações", "Vá para o meu perfil".
    - 'abrir_modal': Use SEMPRE que o usuário pedir para abrir um modal ou janela suspensa na tela:
      * 'automacoes' (opcional: aba_ou_topico='list' para listar ou 'new' para cadastrar nova regra) -> Abre o Gerenciador de Automações
      * 'chave_api' (ou 'configuracoes_ia', 'modelo', 'voz') -> Abre o modal de Configuração de IA & Chave API
      * 'guia' (opcional: aba_ou_topico com tópico como 'visao_geral', 'cameras', 'reconhecimento_facial', 'automacoes', 'slack', 'telegram', 'google', 'sistema', 'musica', 'osint', 'antigravity', 'perfil') -> Abre o Guia Interativo
      * 'webcam' -> Abre a captura de selfie/foto da webcam
      * 'adicionar_comodo' -> Abre o modal de novo cômodo
      * 'camera_fullscreen' -> Abre a câmera em tela cheia
      Exemplos: "Abra o modal de automações", "Abra a tela de criar nova automação", "Abra as configurações de chave API", "Abra o guia do sistema", "Abra a câmera".
    - 'fechar_modal': Use SEMPRE que o usuário pedir para fechar uma janela modal aberta na tela:
      * Aceita 'todos', 'automacoes', 'chave_api', 'guia', 'webcam', 'adicionar_comodo'
      Exemplos: "Feche o modal", "Feche as automações", "Feche a janela", "Feche as configurações".
    - 'alternar_aba_interface': Use quando o usuário pedir para mudar de aba dentro de um modal (ex: 'list' para lista de automações, 'new' para criar nova regra).

REGRAS OBRIGATÓRIAS DE RESPOSTA E FORMATAÇÃO VISUAL:
- Formate sua resposta de maneira elegante e organizada para visualização na tela do chat utilizando Markdown bem estruturado:
  * Utilize tópicos e marcadores de lista ('- ' ou '1. ') para organizar múltiplos itens, resultados ou informações.
  * Destaque palavras-chave, nomes próprios, datas e status em negrito ('**destaque**').
  * Utilize subtítulos ('### Título') para dividir seções em respostas mais detalhadas ou relatórios (ex: OSINT, pesquisas, listas).
  * Sempre que citar links, perfis de redes sociais, artigos, vídeos ou sites da internet, utilize SEMPRE a formatação de link Markdown com texto descritivo e amigável: [Título do Artigo ou Nome da Plataforma](URL) em vez de jogar URLs soltas e desordenadas no texto.
- Responda sempre em português brasileiro de forma educada, prestativa, inteligente e objetiva.
- O sistema possui um pipeline separado que converte automaticamente sua resposta em áudio limpo para a voz, portanto você DEVE incluir links descritivos, formatação e detalhes completos no texto para a melhor experiência visual do usuário na tela do chat.
- Se a solicitação do usuário exigir uma ação (olhar câmera, identificar pessoas, gerenciar notas/listas, gerenciar tarefas, consultar/salvar contatos, consultar/agendar na agenda, ler/enviar/responder e-mail, ligar/desligar luz, consultar status, consultar perfil, buscar na web ou memorizar/consultar fatos aprendidos), invoque a ferramenta correspondente.
"""

    messages = [SystemMessage(content=system_prompt)]
    
    # Injeta as últimas mensagens do histórico se houver
    if chat_history and chat_history[:5]:
        for item in chat_history:
            u_msg = item.get("user_message", "").strip()
            a_msg = item.get("agent_response", "").strip()
            if u_msg:
                messages.append(HumanMessage(content=u_msg))
            if a_msg:
                messages.append(AIMessage(content=a_msg))
                
    # Adiciona a pergunta atual do usuário
    messages.append(HumanMessage(content=prompt_text))
    
    # Modelos candidatos (original + contingência em caso de 503 / sobrecarga / indisponibilidade)
    model_candidates = get_fallback_models(modelo)
    
    executed_reply = None
    last_error = None
    
    for candidate_model in model_candidates:
        try:
            llm = get_chat_model(candidate_model, api_key)
            try:
                model_with_tools = llm.bind_tools(tools)
            except Exception as e:
                agent_logger.warning(f"bind_tools falhou para '{candidate_model}' ({e}), executando llm direto")
                model_with_tools = llm
                
            messages_run = list(messages)
            
            # Loop de execução de ferramentas (Agente ReAct / Tool Calling)
            max_steps = 2
            for step in range(max_steps):
                # Tenta até 2 vezes com pequeno delay em caso de 503 temporário (sobrecarga de servidor)
                ai_msg = None
                for attempt in range(2):
                    try:
                        ai_msg = model_with_tools.invoke(messages_run)
                        break
                    except Exception as invoke_err:
                        err_str = str(invoke_err)
                        if ("503" in err_str or "UNAVAILABLE" in err_str or "high demand" in err_str or "overloaded" in err_str.lower()) and attempt == 0:
                            agent_logger.warning(f"Alta demanda temporária (503) no modelo '{candidate_model}'. Tentando novamente em 1.5s...")
                            time.sleep(1.5)
                            continue
                        raise invoke_err
                
                messages_run.append(ai_msg)
                
                # Se o modelo chamou ferramentas
                if hasattr(ai_msg, "tool_calls") and ai_msg.tool_calls:
                    for tool_call in ai_msg.tool_calls:
                        tool_name = tool_call.get("name")
                        tool_args = tool_call.get("args", {})
                        tool_call_id = tool_call.get("id", tool_name)
                        
                        agent_logger.info(f"[Passo {step+1}] Tool Chamada: '{tool_name}' com argumentos: {tool_args}")
                        if callable(status_cb):
                            try:
                                status_cb("status", get_tool_friendly_status(tool_name), {"tool": tool_name})
                            except Exception:
                                pass
                        
                        selected_tool = tool_map.get(tool_name)
                        if selected_tool:
                            try:
                                tool_output = selected_tool.invoke(tool_args)
                            except Exception as err:
                                tool_output = f"Erro na execução da ferramenta {tool_name}: {err}"
                                agent_logger.error(f"Erro na tool '{tool_name}': {err}")
                        else:
                            tool_output = f"Ferramenta '{tool_name}' não encontrada."
                            agent_logger.warning(tool_output)
                            
                        messages_run.append(ToolMessage(content=str(tool_output), tool_call_id=tool_call_id))
                else:
                    # Resposta final formulada
                    break

            final_msg = messages_run[-1]
            output_text = getattr(final_msg, "content", str(final_msg))
            
            if isinstance(output_text, list) and output_text:
                raw_reply = output_text[0].get("text", str(output_text)) if isinstance(output_text[0], dict) else str(output_text)
            else:
                raw_reply = str(output_text)
                
            display_reply = raw_reply.strip() or "Comando processado com sucesso."
            spoken_reply = gerar_texto_para_fala(display_reply)
            executed_reply = display_reply
            executed_spoken = spoken_reply
            
            if candidate_model != modelo:
                agent_logger.info(f"Comando executado com sucesso utilizando o modelo contingência/fallback '{candidate_model}'")
            break

        except Exception as candidate_err:
            last_error = candidate_err
            err_str = str(candidate_err)
            agent_logger.warning(f"Modelo '{candidate_model}' falhou ({err_str}). Tentando próximo modelo de contingência...")
            continue
            
    if executed_reply is None:
        agent_logger.error(f"Todos os modelos da cadeia de fallback falharam. Último erro: {last_error}")
        display_reply = "Desculpe, os servidores da inteligência artificial estão enfrentando alta demanda temporária neste momento. Por favor, tente novamente em alguns instantes."
        spoken_reply = display_reply
    else:
        display_reply = executed_reply
        spoken_reply = executed_spoken
        
    actions = get_executed_actions()
    agent_logger.info(f"Resposta final (chat): '{display_reply[:90]}...' | Fala (áudio limpo): '{spoken_reply[:80]}...' | Ações: {actions}")
    
    # Dispara o aprendizado contínuo em segundo plano (background thread assíncrona)
    if user_email and api_key and prompt_text:
        try:
            trigger_background_continuous_learning(
                user_message=prompt_text,
                agent_response=display_reply,
                user_email=user_email,
                api_key=api_key,
                model_name=modelo
            )
        except Exception as bg_learn_err:
            agent_logger.warning(f"Falha ao disparar aprendizado contínuo em background: {bg_learn_err}")

    return {
        "reply": display_reply.strip() or "Comando processado com sucesso.",
        "spoken_reply": spoken_reply.strip() or "Comando processado com sucesso.",
        "actions": actions
    }

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
    from api.tools.memory_tools import (
        gravar_memoria_longo_prazo,
        consultar_memorias_longo_prazo,
        listar_todas_memorias,
        esquecer_memoria,
        set_memory_context
    )
    from api.database import db_get_google_credentials, db_get_camera_config, db_get_recent_important_memories_summary
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
    from tools.memory_tools import (
        gravar_memoria_longo_prazo,
        consultar_memorias_longo_prazo,
        listar_todas_memorias,
        esquecer_memoria,
        set_memory_context
    )
    from database import db_get_google_credentials, db_get_camera_config, db_get_recent_important_memories_summary

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

def remover_markdown(texto: str) -> str:
    """Remove caracteres e formatações Markdown para deixar o texto 100% puro para voz e leitura."""
    if not texto:
        return ""
    
    # Remove blocos de código ```...```
    t = re.sub(r'```[\s\S]*?```', '', texto)
    # Remove código inline `...`
    t = re.sub(r'`([^`]+)`', r'\1', t)
    # Remove links [texto](url) -> texto
    # t = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', t)
    # Remove títulos markdown (#, ##, ###)
    t = re.sub(r'^#{1,6}\s+', '', t, flags=re.MULTILINE)
    # Remove negrito e itálico (**texto**, *texto*, __texto__, _texto_)
    t = re.sub(r'\*\*([^*]+)\*\*', r'\1', t)
    t = re.sub(r'\*([^*]+)\*', r'\1', t)
    t = re.sub(r'__([^_]+)__', r'\1', t)
    t = re.sub(r'_([^_]+)_', r'\1', t)
    # Remove marcadores de listas (*, -, + no início da linha)
    t = re.sub(r'^\s*[-*+]\s+', '', t, flags=re.MULTILINE)
    # Remove citações (> texto)
    t = re.sub(r'^\s*>\s+', '', t, flags=re.MULTILINE)
    # Remove linhas horizontais (---, ***)
    t = re.sub(r'^\s*[-*_]{3,}\s*$', '', t, flags=re.MULTILINE)
    # Remove quebras de linha excessivas
    t = re.sub(r'\n{3,}', '\n\n', t)
    return t.strip()

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
        "esquecer_memoria": "Removendo memória do banco de dados..."
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
    set_automation_context(user_email=user_email or "")
    set_system_tools_context(user_email=user_email or "")
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
        gravar_memoria_longo_prazo,
        consultar_memorias_longo_prazo,
        listar_todas_memorias,
        esquecer_memoria,
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
        fechar_navegador_sistema
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
   - 'gravar_memoria_longo_prazo': Use para salvar novos fatos, gostos, preferências, instruções ou detalhes pessoais importantes que o usuário revelar (ex: "Meu time é o Flamengo", "Sou alérgico a camarão", "Sempre que eu pedir pizza, prefira quatro queijos", "Estou estudando Python", "Minha filha se chama Ana"). Você tem autonomia para memorizar fatos valiosos proativamente durante a conversa sempre que o usuário compartilhar informações pessoais ou regras que deseja que você lembre no futuro.
   - 'consultar_memorias_longo_prazo': Use para pesquisar fatos específicos nas memórias gravadas quando o usuário fizer perguntas sobre o que você sabe ou quando precisar resgatar um detalhe passado.
   - 'listar_todas_memorias': Use quando o usuário perguntar o que você lembra sobre ele, quais informações tem salvas ou o que sabe a respeito dele no total.
   - 'esquecer_memoria': Use quando o usuário pedir para você esquecer ou apagar uma informação previamente memorizada.
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
   - 'ver_camera': Use sempre que o usuário pedir para você olhar a câmera, ver o que está no ambiente, o que tem na mesa, descrever o cômodo ou responder a uma pergunta visual.
   - 'detectar_e_cumprimentar_pessoas': Use quando o usuário perguntar se tem alguém na sala, quem está no ambiente ou pedir para você identificar e cumprimentar quem chegou no local. O sistema compara a pessoa filmada com as fotos de perfil dos moradores cadastrados para cumprimentar o morador pelo nome ou tratar como visitante.
   - 'identificar_morador_ou_visitante': Use especificamente quando o usuário perguntar se a pessoa na câmera é um morador oficial da casa ou um visitante, ou perguntar quem está no cômodo e se a pessoa possui cadastro.
   - 'status_camera': Use quando o usuário perguntar se a câmera está funcionando ou qual tipo de câmera está configurada.
8. TELEGRAM & NOTIFICAÇÕES EXTERNAS:
   - 'enviar_mensagem_telegram': Use quando o usuário pedir para enviar um aviso, mensagem ou notificação externa para o Telegram dele (ex: "Me envie uma mensagem no Telegram avisando disso").
   - 'enviar_foto_telegram': Use quando o usuário pedir para capturar a câmera e enviar a foto diretamente no Telegram dele.
9. CONTROLE DE AUTOMAÇÕES E SEGUNDO PLANO:
   - 'listar_automacoes': Use quando o usuário perguntar quais automações estão ativas, o que está agendado, pedir para ver suas regras de segundo plano, regras de câmera/vídeo, lembretes ou resumos.
   - 'controlar_automacao': Use para ativar ('ativar') ou desativar ('desativar') uma regra de automação existente pelo nome ou ID (ex: "Desative a automação do quarto", "Ative a regra de reconhecimento facial", "Desligue o lembrete de reuniões").
   - 'criar_automacao': Use para criar novas regras de automação periódicas, de vídeo ou de agenda conforme pedido pelo usuário.
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

REGRAS OBRIGATÓRIAS DE RESPOSTA E FORMATAÇÃO:
- NUNCA use formatação Markdown (NÃO use asteriscos '**', '#' de títulos, marcadores de lista '-' ou '•', nem itálicos).
- Responda SEMPRE em TEXTO PURO (plain text) contínuo, limpo e direto, otimizado para sintetizadores de voz (TTS).
- Responda sempre em português brasileiro de forma natural, simpática e objetiva.
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
                
            # Sanitiza o texto para remover qualquer markdown residual
            clean_reply = remover_markdown(raw_reply)
            executed_reply = clean_reply.strip() or "Comando processado com sucesso."
            
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
        clean_reply = "Desculpe, os servidores da inteligência artificial estão enfrentando alta demanda temporária neste momento. Por favor, tente novamente em alguns instantes."
    else:
        clean_reply = executed_reply
        
    actions = get_executed_actions()
    agent_logger.info(f"Resposta final formulada (texto puro): '{clean_reply}' | Ações: {actions}")
    
    return {
        "reply": clean_reply.strip() or "Comando processado com sucesso.",
        "actions": actions
    }

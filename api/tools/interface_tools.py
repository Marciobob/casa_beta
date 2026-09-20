import re
from typing import Optional, Dict, Any
from langchain_core.tools import tool

try:
    from api.logger import agent_logger
    from api.tools.mqtt_tools import register_executed_action
except ImportError:
    try:
        from logger import agent_logger
        from tools.mqtt_tools import register_executed_action
    except ImportError:
        import logging
        agent_logger = logging.getLogger("INTERFACE_TOOLS")
        def register_executed_action(action: dict):
            pass

# Mapeamento de telas e URLs da plataforma
SCREEN_MAPPINGS = {
    "dashboard_principal": {"url": "/", "name": "Dashboard Principal (Agente & Chat)"},
    "dashboard_casa": {"url": "/casa.html", "name": "Dashboard da Casa (Smart Home & Cômodos)"},
    "avatar": {"url": "/avatar.html", "name": "Tela do Avatar 2D & Live Stream"},
    "configuracoes": {"url": "/config/config.html", "name": "Configurações da Residência & Broker"},
    "perfil": {"url": "/profile.html", "name": "Perfil do Usuário & Morador"}
}

def normalize_screen_name(input_str: str) -> tuple[str, str]:
    """Normaliza o nome da tela solicitado para a URL e nome amigável."""
    s = (input_str or "").strip().lower()
    
    # 1. Tela do Avatar 2D em Tempo Real
    if any(k in s for k in ["avatar", "assistente visual", "tela do avatar", "ver avatar", "abrir avatar", "mostrar avatar", "live avatar", "avatar 2d", "rosto"]):
        return "/avatar.html", "Tela do Avatar 2D"

    # 2. Perfil do Usuário / Morador
    if any(k in s for k in ["perfil", "morador", "usuario", "usuário", "meus dados", "foto de perfil", "biometria"]):
        return "/profile.html", "Perfil do Usuário"
        
    # 3. Configurações da Residência / Broker MQTT
    if any(k in s for k in ["config", "ajuste", "preferencia", "preferência", "broker", "conexao", "conexão", "mqtt"]):
        return "/config/config.html", "Configurações"
        
    # 4. Dashboard Principal / Painel do Agente / Chat / Início / Terminal
    # Verifica termos específicos do agente/painel principal antes do painel da casa
    if any(k in s for k in [
        "dashboard do agente", "painel do agente", "tela do agente", "agente", "chat",
        "principal", "inicio", "início", "home", "terminal", "painel principal", "dashboard principal", "tela principal"
    ]):
        return "/", "Dashboard Principal"

    # 5. Dashboard da Casa / Smart Home / Cômodos
    if any(k in s for k in ["casa", "smart home", "smarthome", "comodo", "cômodo", "lampada", "lâmpada", "luzes", "residencial", "dashboard da casa", "painel da casa", "tela da casa"]):
        return "/casa.html", "Dashboard da Casa"
        
    return "/", "Dashboard Principal"

def normalize_modal_name(input_str: str) -> tuple[str, str]:
    """Normaliza o identificador do modal solicitado."""
    s = (input_str or "").strip().lower()
    
    # 1. Configurações / Chave de API / IA / Conexões / Voz
    if any(k in s for k in ["chave", "api", "gemini", "openai", "modelo", "voz", "tts", "credencial", "google_config", "config", "ajuste", "preferencia", "preferência", "conexao", "conexão", "telegram", "slack", "gmail"]):
        return "chave_api", "Configurações & Conexões (Chave API & IA)"
        
    # 2. Automações / Tarefas em 2º Plano / Regras / Rotinas
    if any(k in s for k in ["auto", "regra", "rotina", "segundo plano", "agendamento", "monitor", "agendador", "tarefa"]):
        return "automacoes", "Automações e Tarefas em 2º Plano"
        
    # 3. Guia / Manual / Ajuda
    if any(k in s for k in ["guia", "manual", "ajuda", "tutorial", "help", "duvida", "dúvida", "info", "instrucao", "instrução", "instrucoes", "instruções"]):
        return "guia", "Guia & Manual do Sistema"
        
    # 4. Webcam / Captura de Foto
    if any(k in s for k in ["webcam", "selfie", "foto_perfil", "capturar_foto", "camera_perfil", "foto"]):
        return "webcam", "Captura de Foto / Webcam"
        
    # 5. Adicionar Cômodo
    if any(k in s for k in ["novo_comodo", "adicionar_comodo", "comodo_add", "adicionar comodo", "novo cômodo", "novo comodo"]):
        return "adicionar_comodo", "Adicionar Cômodo"
        
    # 6. Câmera Fullscreen
    if any(k in s for k in ["camera_full", "camera_fullscreen", "expandir_camera", "camera_grande", "tela cheia", "fullscreen"]):
        return "camera_fullscreen", "Câmera em Tela Cheia"
        
    if any(k in s for k in ["todos", "tudo", "qualquer", "all"]):
        return "todos", "Todos os Modais"
        
    return "chave_api", "Configurações"

@tool
def navegar_para_tela(tela: str) -> str:
    """
    Navega e muda a tela/dashboard ativo no sistema do usuário de forma autônoma.
    
    Args:
        tela: A tela de destino desejada. Opções principais:
              - 'dashboard_principal' (ou 'agente', 'chat', 'inicio', 'painel principal') -> Página inicial do Agente IA
              - 'dashboard_casa' (ou 'casa', 'smart home', 'cômodos', 'luzes') -> Painel de controle da casa inteligente
              - 'configuracoes' (ou 'config', 'ajustes') -> Painel de configurações MQTT e sistema
              - 'perfil' (ou 'meu perfil', 'morador', 'dados') -> Tela de perfil do usuário e morador
    """
    url, name = normalize_screen_name(tela)
    
    action = {
        "type": "ui_navigate",
        "action_type": "navigate",
        "target": url,
        "name": name
    }
    
    register_executed_action(action)
    agent_logger.info(f"[InterfaceTool] Navegando para tela: '{name}' (URL: '{url}') | Pedido: '{tela}'")
    return f"Navegando para o {name} ({url}). A tela foi alterada com sucesso."

@tool
def abrir_modal(modal: str, aba_ou_topico: Optional[str] = None) -> str:
    """
    Abre um modal ou janela suspensa na interface visual do usuário.
    
    Args:
        modal: O modal que deseja abrir. Opções:
               - 'automacoes' (ou 'regras', 'segundo plano') -> Modal de gerenciador de automações
               - 'chave_api' (ou 'configuracoes_ia', 'voz', 'modelo') -> Modal de configuração de chave de API e IA
               - 'guia' (ou 'manual', 'ajuda') -> Modal de guia interativo e tutoriais
               - 'webcam' -> Modal de selfie e captura de foto no perfil
               - 'adicionar_comodo' -> Modal de cadastro de novo cômodo
               - 'camera_fullscreen' -> Modal de visualização de câmera em tela cheia
        aba_ou_topico: Parâmetro opcional:
               - Para 'automacoes': 'list' (para listar) ou 'new' (para criar nova automação)
               - Para 'guia': tópico específico ('visao_geral', 'cameras', 'reconhecimento_facial', 'automacoes', 'slack', 'telegram', 'google', 'sistema', 'musica', 'osint', 'antigravity', 'perfil')
    """
    norm_modal, display_name = normalize_modal_name(modal)
    
    # Se pediu para criar no modal de automações
    tab = "list"
    if norm_modal == "automacoes":
        if aba_ou_topico and any(k in aba_ou_topico.lower() for k in ["nova", "new", "criar", "cadastrar"]):
            tab = "new"
        elif any(k in modal.lower() for k in ["nova", "new", "criar", "cadastrar"]):
            tab = "new"
            
    topic = "visao_geral"
    if norm_modal == "guia" and aba_ou_topico:
        topic = aba_ou_topico.strip().lower()

    action = {
        "type": "ui_modal",
        "action": "open",
        "action_type": "open_modal",
        "modal": norm_modal,
        "tab": tab,
        "topic": topic,
        "name": display_name
    }
    
    register_executed_action(action)
    agent_logger.info(f"[InterfaceTool] Abrindo modal: '{norm_modal}' (tab: '{tab}', topic: '{topic}')")
    
    detalhes = f" na aba '{tab}'" if norm_modal == "automacoes" and tab == "new" else ""
    if norm_modal == "guia" and topic != "visao_geral":
        detalhes = f" com o tópico '{topic}'"
        
    return f"Modal '{display_name}' aberto na interface do usuário{detalhes}."

@tool
def fechar_modal(modal: Optional[str] = "todos") -> str:
    """
    Fecha a janela modal atualmente aberta na interface do usuário.
    
    Args:
        modal: Opcional. O modal específico a fechar ('automacoes', 'chave_api', 'guia', 'webcam', 'todos'). Se não especificado ou 'todos', fecha qualquer modal atualmente visível.
    """
    raw = (modal or "todos").strip().lower()
    norm_modal = "todos"
    if raw != "todos":
        norm_modal, _ = normalize_modal_name(raw)
        
    action = {
        "type": "ui_modal",
        "action": "close",
        "action_type": "close_modal",
        "modal": norm_modal
    }
    
    register_executed_action(action)
    agent_logger.info(f"[InterfaceTool] Fechando modal: '{norm_modal}'")
    return "Modal fechado na interface com sucesso."

@tool
def alternar_aba_interface(aba: str, contexto: Optional[str] = "automacoes") -> str:
    """
    Alterna abas internas dentro de um modal ou seção da interface visual.
    
    Args:
        aba: A aba para qual alternar:
             - 'list' ou 'lista' -> Aba de listagem de automações
             - 'new', 'nova' ou 'criar' -> Aba de criação de nova automação
        contexto: O contexto onde a aba está localizada (padrão: 'automacoes').
    """
    aba_lower = (aba or "list").strip().lower()
    norm_tab = "list"
    if any(k in aba_lower for k in ["new", "nova", "criar", "adicionar", "cadastro"]):
        norm_tab = "new"
        
    action = {
        "type": "ui_tab",
        "action_type": "switch_tab",
        "tab": norm_tab,
        "context": contexto or "automacoes"
    }
    
    register_executed_action(action)
    agent_logger.info(f"[InterfaceTool] Alternando aba para: '{norm_tab}' no contexto '{contexto}'")
    nome_aba = "Criar Nova Automação" if norm_tab == "new" else "Lista de Automações"
    return f"Aba alternada para '{nome_aba}'."

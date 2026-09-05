import os
import sys
import asyncio
import subprocess
import concurrent.futures
from typing import Optional, Dict, Any, List
from langchain_core.tools import tool

try:
    from api.logger import agent_logger
except ImportError:
    try:
        from logger import agent_logger
    except ImportError:
        import logging
        agent_logger = logging.getLogger("AGENT")

try:
    from api.database import db_get_system_commands_flag, db_get_ai_config
except ImportError:
    try:
        from database import db_get_system_commands_flag, db_get_ai_config
    except ImportError:
        def db_get_system_commands_flag(email: str) -> bool:
            return True
        def db_get_ai_config(email: str) -> Dict[str, Any]:
            return {}

# Contexto ativo
_ACTIVE_ANTIGRAVITY_USER: str = ""
_ACTIVE_ANTIGRAVITY_API_KEY: str = ""
_ACTIVE_ANTIGRAVITY_MODEL: str = "gemini-2.5-flash-lite"
_ANTIGRAVITY_COMMANDS_OVERRIDE: Optional[bool] = None

# Caminhos conhecidos para o binário do agentapi / Antigravity CLI
KNOWN_AGENTAPI_PATHS = [
    "/home/marcio/.gemini/antigravity-ide/bin/agentapi",
    "/home/marcio/.gemini/antigravity/bin/agentapi",
    "/snap/antigravity-ide-snap/current/usr/share/antigravity-ide/resources/app/extensions/antigravity/bin/language_server_linux_x64",
    "agentapi"
]


def set_antigravity_context(user_email: str = "", api_key: str = "", model_name: str = "", commands_enabled: Optional[bool] = None):
    """Configura o contexto de execução para o módulo Antigravity."""
    global _ACTIVE_ANTIGRAVITY_USER, _ACTIVE_ANTIGRAVITY_API_KEY, _ACTIVE_ANTIGRAVITY_MODEL, _ANTIGRAVITY_COMMANDS_OVERRIDE
    _ACTIVE_ANTIGRAVITY_USER = (user_email or "").strip().lower()
    if api_key:
        _ACTIVE_ANTIGRAVITY_API_KEY = api_key.strip()
    if model_name:
        _ACTIVE_ANTIGRAVITY_MODEL = model_name.strip()
    _ANTIGRAVITY_COMMANDS_OVERRIDE = commands_enabled
    agent_logger.info(f"[AntigravityTools] Contexto configurado: usuário='{_ACTIVE_ANTIGRAVITY_USER}', model='{_ACTIVE_ANTIGRAVITY_MODEL}'")


def is_antigravity_commands_allowed() -> bool:
    """Verifica se a execução de comandos físicos via Antigravity está habilitada."""
    if _ANTIGRAVITY_COMMANDS_OVERRIDE is not None:
        return _ANTIGRAVITY_COMMANDS_OVERRIDE
    if _ACTIVE_ANTIGRAVITY_USER:
        try:
            return db_get_system_commands_flag(_ACTIVE_ANTIGRAVITY_USER)
        except Exception as e:
            agent_logger.warning(f"[AntigravityTools] Erro ao consultar permissão: {e}")
    # Por padrão, se não configurado como falso, permite comandos
    return True


def _get_api_key() -> str:
    """Obtém a chave da API do Gemini ativa no contexto, no banco ou no ambiente."""
    if _ACTIVE_ANTIGRAVITY_API_KEY:
        return _ACTIVE_ANTIGRAVITY_API_KEY
    if _ACTIVE_ANTIGRAVITY_USER:
        cfg = db_get_ai_config(_ACTIVE_ANTIGRAVITY_USER)
        if cfg and cfg.get("api_key"):
            return cfg["api_key"]
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or ""


def _run_in_new_thread(coro):
    """Executa uma corotina assíncrona em uma nova thread com seu próprio event loop."""
    def target():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(target)
        return future.result(timeout=60)


async def _async_consult_antigravity_sdk(pergunta: str, contexto: str, api_key: str) -> str:
    """Invoca o agente técnico via SDK google.antigravity."""
    try:
        from google.antigravity import Agent, LocalAgentConfig, CapabilitiesConfig
    except ImportError:
        raise ImportError("google-antigravity SDK não está instalado.")

    system_instructions = (
        "Você é o Agente Especialista Antigravity (Google Antigravity Engine). "
        "Você foi consultado pelo assistente residencial Sexta-Feira para resolver uma dúvida técnica complexa, "
        "análise de arquitetura, diagnóstico de sistema operacional ou desenvolvimento. "
        "Forneça uma resposta precisa, direta, clara e orientada à solução técnica."
    )
    if contexto:
        system_instructions += f"\nContexto adicional fornecido pelo assistente:\n{contexto}"

    config = LocalAgentConfig(
        api_key=api_key if api_key else None,
        system_instructions=system_instructions,
        capabilities=CapabilitiesConfig()
    )

    async with Agent(config) as agent:
        response = await agent.chat(pergunta)
        full_text = ""
        async for token in response:
            full_text += str(token)
        return full_text.strip()


def _consult_antigravity_cli_binary(pergunta: str) -> Optional[str]:
    """Tenta consultar o CLI do Antigravity / agentapi via subprocess se o binário existir."""
    for bin_path in KNOWN_AGENTAPI_PATHS:
        if os.path.exists(bin_path) or (bin_path == "agentapi" and shutil_which("agentapi")):
            try:
                agent_logger.info(f"[AntigravityTools] Tentando consulta via binário CLI: {bin_path}")
                cmd = [bin_path, "new-conversation", "--model=flash", pergunta]
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=5,
                    cwd=os.getcwd()
                )
                if proc.returncode == 0 and proc.stdout.strip():
                    return proc.stdout.strip()
            except Exception as ex:
                agent_logger.warning(f"[AntigravityTools] Falha ao invocar binário '{bin_path}': {ex}")
    return None


def shutil_which(cmd: str) -> Optional[str]:
    import shutil
    return shutil.which(cmd)


def _consult_gemini_fallback(pergunta: str, contexto: str, api_key: str) -> str:
    """Fallback direto usando o modelo Gemini caso o SDK local precise de apoio."""
    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
        from langchain_core.messages import SystemMessage, HumanMessage

        sys_prompt = (
            "Você é o Agente Técnico Especialista Antigravity integrado ao sistema. "
            "Sua função é fornecer respostas técnicas de engenharia, diagnóstico e suporte à tomada de decisões "
            "ao assistente residencial Sexta-Feira. Seja extremamente objetivo, técnico e direto."
        )
        if contexto:
            sys_prompt += f"\nContexto:\n{contexto}"

        llm = ChatGoogleGenerativeAI(
            model=_ACTIVE_ANTIGRAVITY_MODEL or "gemini-2.5-flash-lite",
            google_api_key=api_key,
            temperature=0.2
        )
        res = llm.invoke([SystemMessage(content=sys_prompt), HumanMessage(content=pergunta)])
        return res.content.strip()
    except Exception as e:
        return f"Não foi possível conectar ao motor Antigravity no momento: {str(e)}"


# =========================================================================
# FERRAMENTAS LANGCHAIN EXPOSTAS AO AGENTE SEXTA-FEIRA
# =========================================================================

def _consultar_agente_antigravity_impl(pergunta: str, contexto_adicional: Optional[str] = "") -> str:
    """Implementação interna da consulta ao Antigravity."""
    if not pergunta or not pergunta.strip():
        return "Nenhuma pergunta foi fornecida para o Antigravity."

    agent_logger.info(f"[AntigravityTools] Consultando Antigravity: '{pergunta}'")
    api_key = _get_api_key()

    # 1. Tenta via Python SDK google.antigravity
    try:
        agent_logger.info("[AntigravityTools] Executando consulta via google.antigravity SDK...")
        result = _run_in_new_thread(_async_consult_antigravity_sdk(pergunta, contexto_adicional or "", api_key))
        if result and result.strip():
            agent_logger.info("[AntigravityTools] Resposta obtida com sucesso via SDK!")
            return f"Resposta do Agente Antigravity:\n{result}"
    except Exception as sdk_err:
        agent_logger.warning(f"[AntigravityTools] SDK falhou ({sdk_err}), tentando CLI / Fallback...")

    # 2. Tenta via binário CLI agentapi
    cli_result = _consult_antigravity_cli_binary(pergunta)
    if cli_result:
        return f"Resposta do Antigravity CLI:\n{cli_result}"

    # 3. Fallback via LLM com Persona Antigravity
    if api_key:
        fallback_res = _consult_gemini_fallback(pergunta, contexto_adicional or "", api_key)
        return f"Resposta do Especialista Antigravity:\n{fallback_res}"

    return (
        "O agente Antigravity foi acionado, mas não foi possível estabelecer conexão nem localizar a chave de API Gemini. "
        "Por favor, configure sua chave de API nas configurações do sistema."
    )


# =========================================================================
# FERRAMENTAS LANGCHAIN EXPOSTAS AO AGENTE SEXTA-FEIRA
# =========================================================================

@tool
def consultar_agente_antigravity(pergunta: str, contexto_adicional: Optional[str] = "") -> str:
    """
    Consulta o Agente Especialista Antigravity CLI / SDK para tirar dúvidas avançadas de engenharia, 
    diagnósticos técnicos, arquitetura de software, programação ou resolução de problemas complexos.
    
    Args:
        pergunta: Pergunta, dúvida técnica ou problema a ser analisado pelo Antigravity.
        contexto_adicional: Informações contextuais extras ou logs do sistema para auxiliar na resposta.
    """
    return _consultar_agente_antigravity_impl(pergunta, contexto_adicional)


@tool
def executar_comando_antigravity(comando: str, justificativa: Optional[str] = "") -> str:
    """
    Executa um comando de terminal/shell na máquina física através do motor Antigravity 
    e retorna a saída completa (stdout/stderr), código de saída e tempo de execução.
    
    Args:
        comando: Linha de comando shell a ser executada no sistema operacional Linux (ex: 'df -h', 'uptime', 'systemctl status ...').
        justificativa: Motivo ou objetivo da execução do comando.
    """
    if not comando or not comando.strip():
        return "Nenhum comando foi fornecido para execução."

    clean_cmd = comando.strip()
    agent_logger.info(f"[AntigravityTools] Executando comando na máquina física: '{clean_cmd}' (Justificativa: {justificativa})")

    if not is_antigravity_commands_allowed():
        return (
            "A execução de comandos do sistema operacional na máquina física está atualmente desativada nas suas configurações de IA. "
            "Para permitir que a Sexta-Feira e o Antigravity executem comandos no terminal, ative a opção 'Permitir comandos de sistema' nas configurações."
        )

    # Bloqueio de comandos perigosos de autodestruição do sistema
    cmd_lower = clean_cmd.lower()
    dangerous_patterns = ["rm -rf /", "rm -rf /*", ":(){ :|:& };:", "mkfs", "dd if=/dev/zero", "shutdown -h now", "init 0"]
    for danger in dangerous_patterns:
        if danger in cmd_lower:
            agent_logger.warning(f"[AntigravityTools] Comando bloqueado por segurança: {clean_cmd}")
            return f"O comando '{clean_cmd}' foi bloqueado por questões de segurança do sistema."

    try:
        proc = subprocess.run(
            clean_cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=45,
            cwd=os.getcwd()
        )

        stdout = proc.stdout.strip() if proc.stdout else ""
        stderr = proc.stderr.strip() if proc.stderr else ""
        code = proc.returncode

        # Limita a saída para não exceder limites de contexto
        max_chars = 3000
        if len(stdout) > max_chars:
            stdout = stdout[:max_chars] + f"\n... [Saída truncada: total {len(proc.stdout)} caracteres]"
        if len(stderr) > max_chars:
            stderr = stderr[:max_chars] + f"\n... [Erro truncado: total {len(proc.stderr)} caracteres]"

        if code == 0:
            msg = f"Comando executado com sucesso no sistema (Código 0):\n\n"
            if stdout:
                msg += f"Saída do terminal:\n{stdout}"
            else:
                msg += "Comando concluído sem saída no terminal."
            return msg
        else:
            msg = f"O comando retornou erro com código {code}:\n"
            if stderr:
                msg += f"Erro retornado:\n{stderr}\n"
            if stdout:
                msg += f"Saída padrão:\n{stdout}"
            return msg

    except subprocess.TimeoutExpired:
        agent_logger.error(f"[AntigravityTools] Timeout ao executar comando: {clean_cmd}")
        return f"O comando '{clean_cmd}' atingiu o tempo limite de execução (45 segundos) e foi interrompido."
    except Exception as err:
        agent_logger.error(f"[AntigravityTools] Erro ao executar comando: {err}")
        return f"Falha ao executar comando no sistema: {str(err)}"


@tool
def perguntar_e_executar_antigravity(tarefa: str) -> str:
    """
    Delega uma tarefa técnica complexa ou diagnóstico do computador ao Antigravity.
    O Antigravity analisa a tarefa, propõe a solução e executa os comandos necessários no sistema se autorizado.
    
    Args:
        tarefa: Descrição da tarefa, diagnóstico ou operação desejada no computador.
    """
    if not tarefa or not tarefa.strip():
        return "Nenhuma tarefa fornecida para o Antigravity."

    agent_logger.info(f"[AntigravityTools] Tarefa delegada ao Antigravity: '{tarefa}'")
    api_key = _get_api_key()

    prompt_analise = (
        f"O usuário solicitou a seguinte tarefa no sistema: '{tarefa}'.\n"
        f"Analise o problema e determine a resposta técnica ou o comando bash a ser executado no Linux. "
        f"Se for necessário executar comandos para inspecionar ou solucionar, forneça uma análise clara e o resultado esperado."
    )

    analise = _consultar_agente_antigravity_impl(prompt_analise)
    return analise

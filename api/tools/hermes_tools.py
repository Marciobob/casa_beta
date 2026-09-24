import os
import sys
import re
import json
import time
import shutil
import asyncio
import subprocess
import requests
from typing import Optional, Dict, Any, List, Tuple
try:
    from langchain_core.tools import tool
except ImportError:
    try:
        from langchain.tools import tool
    except ImportError:
        def tool(func):
            func.name = func.__name__
            func.invoke = lambda args: func(**(args if isinstance(args, dict) else {}))
            return func

try:
    from api.logger import agent_logger
except ImportError:
    try:
        from logger import agent_logger
    except ImportError:
        import logging
        agent_logger = logging.getLogger("HERMES_TOOLS")

try:
    from api.database import db_get_ai_config
except ImportError:
    try:
        from database import db_get_ai_config
    except ImportError:
        def db_get_ai_config(email: str) -> Dict[str, Any]:
            return {}

# =========================================================================
# CONTEXTO E CONFIGURAÇÃO ATIVA DO HERMES AGENT
# =========================================================================
_ACTIVE_HERMES_USER: str = ""
_ACTIVE_HERMES_API_KEY: str = ""
_ACTIVE_HERMES_MODEL: str = ""
_ACTIVE_HERMES_GATEWAY_URL: str = os.getenv("HERMES_GATEWAY_URL", "http://localhost:8642/v1")
_ACTIVE_HERMES_TIMEOUT: int = int(os.getenv("HERMES_TIMEOUT_SECONDS", "180"))

# Caminhos conhecidos para o binário / script do Hermes Agent
KNOWN_HERMES_PATHS = [
    os.path.expanduser("~/.local/bin/hermes"),
    os.path.expanduser("~/.hermes/bin/hermes"),
    os.path.expanduser("~/.hermes/hermes-agent/hermes"),
    os.path.expanduser("~/.hermes/venv/bin/hermes"),
    "/usr/local/bin/hermes",
    "hermes"
]


def set_hermes_context(
    user_email: str = "",
    gateway_url: str = "",
    api_key: str = "",
    model_name: str = "",
    timeout: Optional[int] = None
):
    """Configura o contexto de execução para o módulo Hermes Agent."""
    global _ACTIVE_HERMES_USER, _ACTIVE_HERMES_GATEWAY_URL, _ACTIVE_HERMES_API_KEY, _ACTIVE_HERMES_MODEL, _ACTIVE_HERMES_TIMEOUT
    _ACTIVE_HERMES_USER = (user_email or "").strip().lower()
    if gateway_url:
        _ACTIVE_HERMES_GATEWAY_URL = gateway_url.strip().rstrip("/")
    if api_key:
        _ACTIVE_HERMES_API_KEY = api_key.strip()
    if model_name:
        _ACTIVE_HERMES_MODEL = model_name.strip()
    if timeout and timeout > 0:
        _ACTIVE_HERMES_TIMEOUT = timeout
    agent_logger.info(
        f"[HermesTools] Contexto configurado: usuário='{_ACTIVE_HERMES_USER}', "
        f"gateway='{_ACTIVE_HERMES_GATEWAY_URL}', model='{_ACTIVE_HERMES_MODEL or 'default'}'"
    )


def _find_hermes_executable() -> Optional[str]:
    """Localiza o executável do Hermes no sistema."""
    for p in KNOWN_HERMES_PATHS:
        expanded = os.path.expanduser(p)
        if os.path.isfile(expanded) and os.access(expanded, os.X_OK):
            return expanded
        if p == "hermes" and shutil.which("hermes"):
            return shutil.which("hermes")
    return None


def _check_gateway_health(url: str, timeout: float = 2.0) -> bool:
    """Verifica se o servidor de gateway do Hermes está rodando e respondendo."""
    base = url.replace("/v1", "")
    endpoints = [f"{base}/health", f"{url}/models", f"{base}/healthz"]
    for ep in endpoints:
        try:
            r = requests.get(ep, timeout=timeout)
            if r.status_code in (200, 401):  # 401 significa que o endpoint existe e exige auth
                return True
        except Exception:
            continue
    return False


def _get_api_key() -> str:
    """Obtém a chave de autenticação para o Hermes (ou chave Gemini do usuário)."""
    if _ACTIVE_HERMES_API_KEY:
        return _ACTIVE_HERMES_API_KEY
    if _ACTIVE_HERMES_USER:
        cfg = db_get_ai_config(_ACTIVE_HERMES_USER)
        if cfg:
            if cfg.get("hermes_api_key"):
                return cfg["hermes_api_key"]
            if cfg.get("api_key"):
                return cfg["api_key"]
    return os.getenv("HERMES_API_KEY") or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or ""


# =========================================================================
# EXECUÇÃO: REST API GATEWAY & CLI SUBPROCESS
# =========================================================================

def _call_hermes_via_gateway(prompt: str, system_override: Optional[str] = None) -> Optional[str]:
    """Envia o prompt para o Hermes via REST API Gateway (OpenAI-compatible /v1/chat/completions)."""
    endpoint = f"{_ACTIVE_HERMES_GATEWAY_URL}/chat/completions"
    headers = {"Content-Type": "application/json"}
    api_key = _get_api_key()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    messages = []
    if system_override:
        messages.append({"role": "system", "content": system_override})
    messages.append({"role": "user", "content": prompt})

    payload: Dict[str, Any] = {
        "model": _ACTIVE_HERMES_MODEL or "hermes",
        "messages": messages,
        "temperature": 0.4
    }

    try:
        agent_logger.info(f"[HermesTools] Chamando Gateway REST em {endpoint}...")
        resp = requests.post(endpoint, json=payload, headers=headers, timeout=_ACTIVE_HERMES_TIMEOUT)
        if resp.status_code == 200:
            data = resp.json()
            choices = data.get("choices", [])
            if choices and "message" in choices[0]:
                content = choices[0]["message"].get("content", "")
                agent_logger.info("[HermesTools] Resposta recebida via Gateway com sucesso.")
                return content
            return json.dumps(data, ensure_ascii=False)
        else:
            agent_logger.warning(f"[HermesTools] Gateway retornou HTTP {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        agent_logger.warning(f"[HermesTools] Falha ao comunicar com Gateway REST: {e}")
    return None


def _call_hermes_via_cli(prompt: str, extra_flags: Optional[List[str]] = None) -> str:
    """Executa a tarefa no Hermes via comando CLI (--oneshot / -q)."""
    bin_path = _find_hermes_executable()
    if not bin_path:
        return (
            "Erro: O executável do Hermes Agent não foi encontrado no sistema. "
            "Certifique-se de que o Hermes foi instalado em ~/.hermes/hermes-agent ou no PATH."
        )

    cmd = [bin_path, "chat", "-q", prompt]
    if extra_flags:
        cmd.extend(extra_flags)

    # Injeta variáveis de ambiente úteis
    env = os.environ.copy()
    env["HERMES_SINGLE_QUERY_SESSION"] = "1"
    env["HERMES_SESSION_SOURCE"] = "casa_beta_orchestrator"
    # Garante que o Node e o venv do Hermes estejam no PATH do subprocesso
    hermes_home = os.path.expanduser("~/.hermes")
    venv_bin = os.path.join(hermes_home, "venv", "bin")
    node_bin = os.path.join(hermes_home, "node", "bin")
    current_path = env.get("PATH", "")
    env["PATH"] = f"{venv_bin}:{node_bin}:{hermes_home}/bin:{current_path}"

    api_key = _get_api_key()
    if api_key:
        env["GEMINI_API_KEY"] = api_key
        env["GOOGLE_API_KEY"] = api_key

    agent_logger.info(f"[HermesTools] Executando comando CLI: {' '.join(cmd[:5])}...")
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=_ACTIVE_HERMES_TIMEOUT,
            cwd=os.path.expanduser("~"),
            env=env
        )
        stdout = proc.stdout.strip()
        stderr = proc.stderr.strip()

        if proc.returncode == 0 and stdout:
            agent_logger.info("[HermesTools] Execução CLI finalizada com sucesso.")
            return _clean_hermes_output(stdout)
        elif stdout:
            cleaned = _clean_hermes_output(stdout)
            return f"{cleaned}\n\n(Aviso/Stderr: {stderr[:300]})" if stderr else cleaned
        elif stderr:
            return f"Erro na execução do Hermes CLI (código {proc.returncode}):\n{stderr}"
        else:
            return f"O Hermes CLI finalizou com código {proc.returncode}, mas sem saída de texto."
    except subprocess.TimeoutExpired:
        agent_logger.error(f"[HermesTools] Timeout de {_ACTIVE_HERMES_TIMEOUT}s excedido ao executar Hermes.")
        return f"Tempo limite de execução excedido ({_ACTIVE_HERMES_TIMEOUT} segundos). A tarefa era muito extensa."
    except Exception as ex:
        agent_logger.error(f"[HermesTools] Exceção ao executar Hermes CLI: {ex}")
        return f"Falha na execução do processo Hermes Agent: {str(ex)}"


def _clean_hermes_output(text: str) -> str:
    """Extrai apenas a resposta textual relevante do Hermes Agent eliminando decorações TUI."""
    if not text:
        return ""
    # Se contiver a caixa '╭─ ☤ Hermes ... ╰─'
    box_match = re.search(r'╭─[^\n]*Hermes[^\n]*\n([\s\S]*?)\n╰─', text)
    if box_match:
        return box_match.group(1).strip()
    # Se contiver 'Resume this session with:' remove o rodapé de sessão
    parts = re.split(r'Resume this session with:', text, maxsplit=1)
    cleaned = parts[0].strip()
    # Remove prefixo de Query / Initializing
    cleaned = re.sub(r'^Query:[\s\S]*?────────────────────────────────────────\s*', '', cleaned)
    return cleaned.strip() if cleaned else text.strip()


def _dispatch_hermes(prompt: str, system_override: Optional[str] = None) -> str:
    """Despacha a requisição para o Hermes: tenta primeiro via Gateway REST; fallback para CLI."""
    if _check_gateway_health(_ACTIVE_HERMES_GATEWAY_URL, timeout=1.5):
        result = _call_hermes_via_gateway(prompt, system_override=system_override)
        if result:
            return result
    # Fallback transparente para o CLI
    return _call_hermes_via_cli(prompt)


# =========================================================================
# FERRAMENTAS LANGCHAIN EXPOSTAS AO AGENTE ORQUESTRADOR (SEXTA-FEIRA)
# =========================================================================

@tool
def delegar_tarefa_hermes(tarefa: str, contexto_adicional: Optional[str] = "") -> str:
    """Delega uma tarefa complexa, autônoma, analítica ou multi-etapas para o Hermes Agent (Nous Research).
    Use SEMPRE que:
    1. A tarefa exigir raciocínio profundo, resolução em múltiplas etapas ou pesquisa técnica avançada.
    2. O usuário pedir explicitamente para delegar ou perguntar ao Hermes ('Hermes, faça...', 'pede pro Hermes...').
    3. For necessário analisar grandes volumes de dados ou sintetizar relatórios detalhados com autonomia.
    O Hermes atuará como seu subagente especialista executor e devolverá o resultado consolidado."""
    if not tarefa or not tarefa.strip():
        return "Erro: Nenhuma tarefa foi especificada para delegar ao Hermes Agent."

    prompt = f"Tarefa delegada pelo Agente Orquestrador Central:\n{tarefa.strip()}"
    if contexto_adicional and contexto_adicional.strip():
        prompt += f"\n\nContexto fornecido:\n{contexto_adicional.strip()}"

    sys_instr = (
        "Você é o Hermes Agent (Nous Research), atuando como subagente especialista em execução e raciocínio profundo "
        "sob a orquestração do assistente central Sexta-Feira. Resolva a tarefa com rigor técnico, execute as análises necessárias "
        "e retorne uma resposta conclusiva, detalhada e estruturada em Markdown."
    )
    return _dispatch_hermes(prompt, system_override=sys_instr)


@tool
def executar_pesquisa_profunda_hermes(tema: str, objetivo: Optional[str] = "") -> str:
    """Aciona o Hermes Agent para conduzir uma pesquisa aprofundada na web, explorando múltiplas fontes,
    sintetizando descobertas e gerando um relatório completo com referências.
    Use quando o usuário pedir um estudo detalhado, dossiê, análise de mercado ou pesquisa exaustiva."""
    if not tema or not tema.strip():
        return "Erro: Nenhum tema fornecido para a pesquisa profunda."

    prompt = (
        f"Realize uma pesquisa aprofundada, abrangente e detalhada sobre o seguinte tema:\n"
        f"Tema: {tema.strip()}\n"
    )
    if objetivo:
        prompt += f"Objetivo específico: {objetivo.strip()}\n"
    prompt += (
        "\nEstruture a resposta com: Resumo Executivo, Pontos-Chave, Análise Crítica, "
        "Tendências/Implicações e Fontes/Referências."
    )

    sys_instr = "Você é o especialista de pesquisa e inteligência do Hermes Agent. Produza relatórios de alto nível analítico."
    return _dispatch_hermes(prompt, system_override=sys_instr)


@tool
def executar_codigo_sandbox_hermes(codigo_ou_comando: str, contexto: Optional[str] = "") -> str:
    """Solicita ao Hermes Agent que execute, teste ou valide um script, comando ou código em seu ambiente de execução.
    O Hermes executará o código, capturará as saídas (stdout/stderr) e fornecerá diagnóstico caso haja erros."""
    if not codigo_ou_comando or not codigo_ou_comando.strip():
        return "Erro: Nenhum código ou comando fornecido para execução."

    prompt = (
        f"Por favor, execute e avalie o seguinte código/comando no seu ambiente de execução:\n\n"
        f"```\n{codigo_ou_comando.strip()}\n```\n"
    )
    if contexto:
        prompt += f"\nContexto adicional:\n{contexto.strip()}\n"
    prompt += "\nRetorne a saída real da execução, o status de sucesso/falha e um diagnóstico caso haja erros."

    sys_instr = "Você é o motor de execução de código e diagnósticos do Hermes Agent. Seja técnico e preciso."
    return _dispatch_hermes(prompt, system_override=sys_instr)


@tool
def consultar_skills_hermes() -> str:
    """Consulta as habilidades (skills), plugins e extensões autônomas atualmente disponíveis e aprendidas no Hermes Agent."""
    hermes_home = os.path.expanduser("~/.hermes")
    skills_dir = os.path.join(hermes_home, "skills")

    found_skills: Dict[str, List[str]] = {}
    if os.path.isdir(skills_dir):
        try:
            for cat in sorted(os.listdir(skills_dir)):
                cat_path = os.path.join(skills_dir, cat)
                if os.path.isdir(cat_path) and not cat.startswith("."):
                    sub_items = []
                    for item in sorted(os.listdir(cat_path)):
                        item_path = os.path.join(cat_path, item)
                        if os.path.isdir(item_path):
                            readme = os.path.join(item_path, "SKILL.md")
                            desc = ""
                            if os.path.exists(readme):
                                with open(readme, "r", encoding="utf-8", errors="ignore") as f:
                                    lines = [f.readline() for _ in range(12)]
                                    for line in lines:
                                        line_s = line.strip()
                                        if line_s.startswith("description:"):
                                            desc = line_s.replace("description:", "").strip().strip('"\'')
                                            break
                            sub_items.append(f"`{item}` ({desc[:60]}...)" if desc else f"`{item}`")
                    if sub_items:
                        found_skills[cat] = sub_items
        except Exception as e:
            agent_logger.warning(f"[HermesTools] Erro ao listar skills do Hermes: {e}")

    if not found_skills:
        return "Nenhuma skill personalizada localizada em ~/.hermes/skills."

    total_count = sum(len(items) for items in found_skills.values())
    res = f"🧠 **Habilidades (Skills) do Hermes Agent ({total_count} skills ativas):**\n"
    for cat, items in found_skills.items():
        res += f"\n📂 **{cat.title().replace('-', ' ')}** ({len(items)}):\n"
        res += "  • " + ", ".join(items) + "\n"
    return res


@tool
def status_hermes_agent() -> str:
    """Verifica e retorna o status atual da integração com o Hermes Agent:
    se o binário está instalado, se o Gateway REST está ativo na porta 8642, e as configurações vigentes."""
    bin_path = _find_hermes_executable()
    installed = bin_path is not None
    gateway_online = _check_gateway_health(_ACTIVE_HERMES_GATEWAY_URL, timeout=1.5)

    status_info = {
        "instalado": installed,
        "caminho_executavel": bin_path or "Não encontrado",
        "gateway_url": _ACTIVE_HERMES_GATEWAY_URL,
        "gateway_online": gateway_online,
        "modelo_configurado": _ACTIVE_HERMES_MODEL or "hermes (padrão)",
        "timeout_segundos": _ACTIVE_HERMES_TIMEOUT,
        "usuario_ativo": _ACTIVE_HERMES_USER or "Padrão do sistema"
    }

    txt = "📊 **Status do Hermes Agent:**\n"
    txt += f"- **Instalação:** {'✅ Instalado' if installed else '❌ Não localizado'}\n"
    if installed:
        txt += f"  - Executável: `{bin_path}`\n"
    txt += f"- **Gateway REST:** {'🟢 Online' if gateway_online else '⚪ Offline (fallback CLI ativo)'}\n"
    txt += f"  - URL: `{_ACTIVE_HERMES_GATEWAY_URL}`\n"
    txt += f"- **Modelo:** `{status_info['modelo_configurado']}`\n"
    txt += f"- **Modo de Operação:** {'Gateway REST (alta performance)' if gateway_online else 'CLI Subprocess (autônomo)'}\n"
    return txt

import os
import re
import sys
import shutil
import subprocess
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
    from api.tools.antigravity_tools import _consultar_agente_antigravity_impl, _get_api_key
except ImportError:
    try:
        from tools.antigravity_tools import _consultar_agente_antigravity_impl, _get_api_key
    except ImportError:
        def _consultar_agente_antigravity_impl(pergunta: str, contexto_adicional: Optional[str] = "") -> str:
            return f"[Antigravity Fallback] Dados brutos analisados:\n{contexto_adicional}\n\n{pergunta}"
        def _get_api_key() -> str:
            return os.environ.get("GEMINI_API_KEY", "")

try:
    from api.tools.search_tools import pesquisar_na_internet
except ImportError:
    try:
        from tools.search_tools import pesquisar_na_internet
    except ImportError:
        pesquisar_na_internet = None


# Contexto de execução OSINT
_ACTIVE_OSINT_USER: str = ""
_ACTIVE_OSINT_API_KEY: str = ""
_ACTIVE_OSINT_MODEL: str = "gemini-2.5-flash-lite"


def set_osint_context(user_email: str = "", api_key: str = "", model_name: str = ""):
    """Configura o contexto de usuário e modelo para as ferramentas de OSINT."""
    global _ACTIVE_OSINT_USER, _ACTIVE_OSINT_API_KEY, _ACTIVE_OSINT_MODEL
    _ACTIVE_OSINT_USER = (user_email or "").strip().lower()
    if api_key:
        _ACTIVE_OSINT_API_KEY = api_key.strip()
    if model_name:
        _ACTIVE_OSINT_MODEL = model_name.strip()
    agent_logger.info(f"[OSINTTools] Contexto configurado: usuário='{_ACTIVE_OSINT_USER}', model='{_ACTIVE_OSINT_MODEL}'")


def clean_target_username(raw: str) -> str:
    """
    Limpa e normaliza o username ou handle do Instagram/redes sociais.
    Remove '@', URLs de perfis (ex: instagram.com/usuario/), barras e parâmetros.
    """
    if not raw:
        return ""
    clean = raw.strip()
    
    # Remove prefixo de URL do Instagram ou outras redes
    clean = re.sub(r'^https?:\/\/(?:www\.)?instagram\.com\/', '', clean, flags=re.IGNORECASE)
    clean = re.sub(r'^https?:\/\/(?:www\.)?(?:twitter|x|github|tiktok)\.com\/', '', clean, flags=re.IGNORECASE)
    
    # Remove query strings e barras finais
    clean = clean.split('?')[0].split('#')[0].rstrip('/')
    # Remove o '@' inicial
    clean = clean.lstrip('@').strip()
    return clean


def get_sherlock_executable() -> List[str]:
    """Retorna o comando executável do Sherlock."""
    # 1. Caminho local de instalação do usuário
    user_sherlock = os.path.expanduser("~/.local/bin/sherlock")
    if os.path.exists(user_sherlock) and os.access(user_sherlock, os.X_OK):
        return [user_sherlock]

    # 2. No PATH do sistema
    which_sh = shutil.which("sherlock")
    if which_sh:
        return [which_sh]

    # 3. Via Python do sistema
    return ["/usr/bin/python3", "-m", "sherlock_project"]


def get_holehe_executable() -> List[str]:
    """Retorna o executável do Holehe."""
    candidates = [
        "/home/marcio/anaconda3/envs/agente/bin/holehe",
        os.path.expanduser("~/.local/bin/holehe"),
        shutil.which("holehe")
    ]
    for c in candidates:
        if c and os.path.exists(c) and os.access(c, os.X_OK):
            return [c]
    return ["holehe"]


def run_sherlock_scan(username: str, timeout_sec: int = 5, max_results: int = 40) -> Dict[str, Any]:
    """
    Executa a ferramenta Sherlock (Kali Linux) para mapear perfis ativos do usuário em redes sociais.
    """
    clean_user = clean_target_username(username)
    if not clean_user:
        return {"success": False, "error": "Nome de usuário inválido ou vazio.", "profiles": []}

    agent_logger.info(f"[OSINTTools] Iniciando varredura Sherlock para: '{clean_user}'")
    sherlock_cmd = get_sherlock_executable()
    cmd = sherlock_cmd + [
        "--print-found",
        "--no-color",
        "--timeout", str(timeout_sec),
        clean_user
    ]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=35,
            cwd=os.getcwd()
        )
        output = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
        
        found_profiles = []
        # Expressão regular para capturar linhas de perfis encontrados pelo Sherlock: [+] Plataforma: URL
        pattern = re.compile(r'\[\+\]\s*([^:]+):\s*(https?:\/\/[^\s]+)', re.IGNORECASE)
        for line in output.splitlines():
            match = pattern.search(line)
            if match:
                platform = match.group(1).strip()
                url = match.group(2).strip()
                found_profiles.append({"platform": platform, "url": url})

        # Limita quantidade de perfis para não sobrecarregar
        if max_results and len(found_profiles) > max_results:
            found_profiles = found_profiles[:max_results]

        agent_logger.info(f"[OSINTTools] Sherlock concluído para '{clean_user}': {len(found_profiles)} perfis encontrados.")
        return {
            "success": True,
            "username": clean_user,
            "count": len(found_profiles),
            "profiles": found_profiles,
            "raw_output": output[:3000]
        }
    except subprocess.TimeoutExpired:
        agent_logger.warning(f"[OSINTTools] Sherlock atingiu timeout para '{clean_user}'.")
        return {"success": False, "error": "A varredura Sherlock atingiu o limite de tempo (35 segundos).", "profiles": []}
    except Exception as e:
        agent_logger.error(f"[OSINTTools] Erro ao executar Sherlock: {e}")
        return {"success": False, "error": str(e), "profiles": []}


def run_holehe_scan(email: str, timeout_sec: int = 5) -> Dict[str, Any]:
    """
    Executa a ferramenta Holehe (Kali Linux) para verificar em quais serviços um e-mail está cadastrado.
    """
    clean_email = email.strip()
    if not clean_email or "@" not in clean_email:
        return {"success": False, "error": "E-mail inválido.", "accounts": []}

    agent_logger.info(f"[OSINTTools] Iniciando verificação Holehe para: '{clean_email}'")
    holehe_cmd = get_holehe_executable()
    cmd = holehe_cmd + [
        "--only-used",
        "--no-color",
        "--no-clear",
        "-NP",
        "-T", str(timeout_sec),
        clean_email
    ]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=25,
            cwd=os.getcwd()
        )
        output = proc.stdout or ""
        
        found_accounts = []
        for line in output.splitlines():
            clean_l = line.strip()
            if clean_l.startswith("[+]"):
                account_site = clean_l.replace("[+]", "").strip()
                if account_site and not account_site.startswith("Email used"):
                    found_accounts.append(account_site)

        agent_logger.info(f"[OSINTTools] Holehe concluído para '{clean_email}': {len(found_accounts)} contas encontradas.")
        return {
            "success": True,
            "email": clean_email,
            "count": len(found_accounts),
            "accounts": found_accounts,
            "raw_output": output[:2000]
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "A verificação Holehe atingiu o limite de tempo.", "accounts": []}
    except Exception as e:
        agent_logger.error(f"[OSINTTools] Erro ao executar Holehe: {e}")
        return {"success": False, "error": str(e), "accounts": []}


def run_dns_dig_scan(target_domain: str) -> Dict[str, Any]:
    """Executa consultas de DNS (dig) para extrair registros A, MX e TXT de um domínio associado."""
    domain = target_domain.strip().lower()
    # Remove prefixo de protocolo
    domain = re.sub(r'^https?:\/\/', '', domain).split('/')[0].strip()
    if not domain or "." not in domain:
        return {"success": False, "error": "Domínio inválido.", "records": {}}

    agent_logger.info(f"[OSINTTools] Consultando DNS dig para: '{domain}'")
    records = {}
    for rtype in ["A", "MX", "TXT"]:
        try:
            res = subprocess.run(["dig", "+short", rtype, domain], capture_output=True, text=True, timeout=5)
            lines = [l.strip() for l in (res.stdout or "").splitlines() if l.strip()]
            if lines:
                records[rtype] = lines
        except Exception:
            pass

    return {"success": True, "domain": domain, "records": records}


def run_web_osint_search(query: str) -> List[str]:
    """Executa dorking OSINT na web para buscar menções do alvo."""
    if not pesquisar_na_internet:
        return []
    try:
        raw_res = pesquisar_na_internet.invoke({"consulta": query})
        if raw_res and not raw_res.startswith("Erro") and not raw_res.startswith("Nenhum"):
            return [raw_res]
    except Exception as e:
        agent_logger.warning(f"[OSINTTools] Erro na busca web: {e}")
    return []


def sintetizar_dossie_com_antigravity(
    nome_alvo: str,
    username: str,
    dados_osint: Dict[str, Any],
    info_adicional: str = ""
) -> str:
    """
    Aciona o Agente Especialista Antigravity para analisar todos os dados OSINT coletados
    e compilar um dossiê executivo de inteligência estruturado.
    """
    resumo_dados = []
    
    # 1. Perfis encontrados pelo Sherlock
    sherlock_res = dados_osint.get("sherlock", {})
    profiles = sherlock_res.get("profiles", [])
    if profiles:
        resumo_dados.append(f"### Redes Sociais e Perfis Detectados (Sherlock - {len(profiles)} encontrados):")
        for p in profiles:
            resumo_dados.append(f"- **{p['platform']}**: {p['url']}")
    else:
        resumo_dados.append("### Redes Sociais Detectadas: Nenhuma conta pública mapeada pelo Sherlock para esse username específico.")

    # 2. Contas de e-mail (Holehe)
    holehe_res = dados_osint.get("holehe", {})
    accounts = holehe_res.get("accounts", [])
    if accounts:
        resumo_dados.append(f"\n### Plataformas com Cadastro Vinculado ao E-mail ({len(accounts)} serviços):")
        for acc in accounts:
            resumo_dados.append(f"- {acc}")

    # 3. Pesquisa na Web / Dorking
    web_res = dados_osint.get("web_search", [])
    if web_res:
        resumo_dados.append(f"\n### Menções e Pegada Digital Indexada na Web:\n" + "\n\n".join(web_res))

    # 4. Registros de Domínio / DNS
    dns_res = dados_osint.get("dns", {})
    if dns_res.get("records"):
        resumo_dados.append(f"\n### Registros de Infraestrutura e DNS do Domínio ({dns_res.get('domain')}):")
        for rtype, rvals in dns_res["records"].items():
            resumo_dados.append(f"- {rtype}: {', '.join(rvals)}")

    if info_adicional:
        resumo_dados.append(f"\n### Informações de Contexto Fornecidas pelo Usuário:\n{info_adicional}")

    dados_compilados_str = "\n".join(resumo_dados)

    prompt_analista = (
        f"Você é o Agente Especialista Antigravity atuando como Analista Sênior de Inteligência em Fontes Abertas (OSINT Analyst).\n"
        f"Analise o seguinte compilado de dados brutos coletados sobre o alvo:\n"
        f"Nome/Alvo: '{nome_alvo or 'Não informado'}'\n"
        f"Username / @ do Instagram: '{username or 'Não informado'}'\n\n"
        f"DADOS COLETADOS:\n{dados_compilados_str}\n\n"
        f"SUA TAREFA:\n"
        f"Gere um Dossiê de Inteligência OSINT estruturado, profissional, visualmente elegante e objetivo contendo:\n"
        f"1. 👤 Identificação & Presença Digital: Nome, pseudônimo (@{username}) e resumo do perfil encontrado.\n"
        f"2. 🌐 Principais Redes e Plataformas Confirmadas: Destaque os links no formato amigável de link Markdown [Nome da Rede](URL) (ex: [Instagram](https://...), [GitHub](https://...), [LinkedIn](https://...)). Evite URLs soltas sem descrição.\n"
        f"3. 🔍 Cruzamento de Informações & Insights: Atividades profissionais, interesses, áreas de atuação e consistência dos perfis.\n"
        f"4. 🛡️ Nível de Exposição Digital & Recomendações: Avaliação da pegada digital do alvo e próximos passos sugeridos de verificação.\n"
        f"Forneça o relatório com excelente formatação em tópicos e subtítulos Markdown claros."
    )

    try:
        relatorio = _consultar_agente_antigravity_impl(
            prompt_analista,
            contexto_adicional=f"Alvo OSINT: {nome_alvo or username}"
        )
        return relatorio
    except Exception as e:
        agent_logger.error(f"[OSINTTools] Erro ao sintetizar dossiê com Antigravity: {e}")
        # Fallback direto caso o Antigravity falhe
        return (
            f"## Dossiê OSINT - {nome_alvo or username}\n\n"
            f"{dados_compilados_str}"
        )


# =========================================================================
# FERRAMENTAS LANGCHAIN EXPOSTAS AO AGENTE SEXTA-FEIRA
# =========================================================================

@tool
def investigar_pessoa_osint(
    nome_ou_alvo: str,
    instagram_ou_usuario: Optional[str] = "",
    informacoes_adicionais: Optional[str] = ""
) -> str:
    """
    Realiza uma investigação completa de OSINT (Open Source Intelligence) sobre uma pessoa ou perfil,
    utilizando ferramentas do Kali Linux (Sherlock, Holehe, DNS) e o Agente Especialista Antigravity.
    
    Recebe um nome completo, arroba do Instagram (@usuario), username de rede social ou dados complementares,
    mapeia a pegada digital na internet e gera um dossiê analítico detalhado.
    
    Args:
        nome_ou_alvo: Nome da pessoa, alvo de pesquisa ou termo principal (ex: 'Marcio Silva', 'João Souza').
        instagram_ou_usuario: Arroba (@usuario) ou username de redes sociais (ex: '@marciobob', 'marcio_dev').
        informacoes_adicionais: Detalhes extras úteis para afunilar a busca (ex: cidade, profissão, e-mail, empresa).
    """
    alvo_principal = (nome_ou_alvo or "").strip()
    usuario_alvo = clean_target_username(instagram_ou_usuario or "")

    # Se o nome fornecido já tiver formato de arroba (@usuario) e não foi passado usuario explicitamente
    if not usuario_alvo and alvo_principal.startswith("@"):
        usuario_alvo = clean_target_username(alvo_principal)

    # Se apenas o usuário foi passado como nome
    if not usuario_alvo and re.match(r'^[a-zA-Z0-9_\-\.]{3,30}$', alvo_principal) and not " " in alvo_principal:
        usuario_alvo = alvo_principal

    if not alvo_principal and not usuario_alvo:
        return "Informe o nome de uma pessoa ou um arroba (@usuario) para iniciar a investigação OSINT."

    agent_logger.info(f"[OSINTTools] Nova investigação OSINT solicitada para Alvo: '{alvo_principal}', User: '{usuario_alvo}'")

    dados_coletados = {
        "sherlock": {},
        "holehe": {},
        "web_search": [],
        "dns": {}
    }

    # 1. Executa o Sherlock se tivermos um username / arroba
    if usuario_alvo:
        sherlock_res = run_sherlock_scan(usuario_alvo, timeout_sec=5, max_results=35)
        dados_coletados["sherlock"] = sherlock_res

    # 2. Extrai ou verifica e-mails nas informações adicionais
    email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', f"{alvo_principal} {informacoes_adicionais}")
    if email_match:
        target_email = email_match.group(0)
        holehe_res = run_holehe_scan(target_email, timeout_sec=5)
        dados_coletados["holehe"] = holehe_res
        
        # Consulta DNS do domínio do e-mail
        domain_part = target_email.split("@")[-1]
        if domain_part not in ["gmail.com", "hotmail.com", "outlook.com", "yahoo.com"]:
            dados_coletados["dns"] = run_dns_dig_scan(domain_part)

    # 3. Pesquisa web / Dorking direcionado
    termos_busca = []
    if alvo_principal and usuario_alvo and alvo_principal.lower() != usuario_alvo.lower():
        termos_busca.append(f'"{alvo_principal}" "{usuario_alvo}"')
    elif usuario_alvo:
        termos_busca.append(f'site:instagram.com "{usuario_alvo}"')
        termos_busca.append(f'"{usuario_alvo}" (github OR linkedin OR twitter OR instagram)')
    elif alvo_principal:
        termos_busca.append(f'"{alvo_principal}" site:linkedin.com/in/')
        if informacoes_adicionais:
            termos_busca.append(f'"{alvo_principal}" {informacoes_adicionais}')

    for t in termos_busca[:2]:
        achados = run_web_osint_search(t)
        if achados:
            dados_coletados["web_search"].extend(achados)

    # 4. Sintetiza o Dossiê Final com o Agente Especialista Antigravity
    dossie_final = sintetizar_dossie_com_antigravity(
        nome_alvo=alvo_principal,
        username=usuario_alvo,
        dados_osint=dados_coletados,
        info_adicional=informacoes_adicionais or ""
    )

    return dossie_final


@tool
def buscar_usuario_redes_sociais_sherlock(usuario_ou_arroba: str) -> str:
    """
    Utiliza a ferramenta Sherlock (Kali Linux) para buscar e descobrir todas as contas 
    e perfis existentes de um @username nas redes sociais (Instagram, GitHub, Twitter, TikTok, Telegram, etc.).
    
    Args:
        usuario_ou_arroba: Arroba ou username a ser rastreado (ex: '@marciobob', 'marcio_dev').
    """
    clean_user = clean_target_username(usuario_ou_arroba)
    if not clean_user:
        return "Por favor, forneça um nome de usuário ou arroba válido para busca no Sherlock."

    res = run_sherlock_scan(clean_user, timeout_sec=5, max_results=50)
    if not res.get("success"):
        return f"Erro na execução do Sherlock: {res.get('error', 'Falha desconhecida')}"

    profiles = res.get("profiles", [])
    if not profiles:
        return f"Nenhum perfil público ativo foi encontrado para o usuário '@{clean_user}' no momento."

    linhas = [f"🔎 **Varredura Sherlock Concluída para '@{clean_user}'** ({len(profiles)} perfis encontrados):\n"]
    for p in profiles:
        linhas.append(f"- **{p['platform']}**: {p['url']}")

    return "\n".join(linhas)


@tool
def verificar_email_osint_holehe(email: str) -> str:
    """
    Utiliza a ferramenta Holehe (Kali Linux) para verificar em mais de 120 serviços e plataformas 
    da internet se um endereço de e-mail possui cadastro ativo (sem disparar tentativas de redefinição de senha).
    
    Args:
        email: Endereço de e-mail alvo para verificação de contas existentes.
    """
    clean_email = (email or "").strip()
    if not clean_email or "@" not in clean_email:
        return "Por favor, forneça um endereço de e-mail válido."

    res = run_holehe_scan(clean_email, timeout_sec=6)
    if not res.get("success"):
        return f"Erro na verificação Holehe: {res.get('error', 'Falha desconhecida')}"

    accounts = res.get("accounts", [])
    if not accounts:
        return f"Nenhuma conta ativa foi detectada publicamente para o e-mail '{clean_email}'."

    linhas = [f"📧 **Verificação Holehe Concluída para '{clean_email}'** ({len(accounts)} serviços detectados):\n"]
    for acc in accounts:
        linhas.append(f"- ✅ {acc}")

    return "\n".join(linhas)

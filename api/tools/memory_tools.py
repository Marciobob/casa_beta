"""
Ferramentas LangChain para Memória de Longo Prazo e Aprendizado Autônomo do Agente.
Permite ao assistente de IA decidir ativamente e gravar fatos valiosos sobre o usuário,
preferências, hábitos, rotinas, instruções e contexto histórico, além de consultar e gerenciar essas memórias.

Inclui motor de aprendizado contínuo assíncrono em background (thread não-bloqueante) para
garantir máxima velocidade e tempo de resposta zero para o usuário na conversa principal.
"""

import os
import re
import json
import threading
from typing import List, Dict, Any, Optional
from langchain_core.tools import tool

try:
    from api.logger import system_logger
    from api.database import (
        db_save_agent_memory,
        db_search_agent_memories,
        db_get_all_agent_memories,
        db_delete_agent_memory,
        db_get_recent_important_memories_summary
    )
except ImportError:
    from logger import system_logger
    from database import (
        db_save_agent_memory,
        db_search_agent_memories,
        db_get_all_agent_memories,
        db_delete_agent_memory,
        db_get_recent_important_memories_summary
    )

_MEMORY_USER_EMAIL: Optional[str] = None

# Expressão regular para detecção rápida (pré-filtro de alta performance) de potenciais fatos duradouros
LEARNING_INDICATORS_REGEX = re.compile(
    r"\b("
    r"eu sou|meu nome|minha idade|moro em|moro no|moro na|minha casa|"
    r"gosto de|não gosto de|odeio|adoro|prefiro|preferência|minha preferência|"
    r"meu time|torço|minha filha|meu filho|minha esposa|meu marido|meu namorado|minha namorada|"
    r"meu irmão|minha irmã|meu pai|minha mãe|minha família|"
    r"minha profissão|trabalho como|trabalho na|trabalho no|trabalho com|minha empresa|"
    r"estudo|sou formado|estudando|"
    r"alérgico|alérgica|alergia|intolerante|diabético|vegetariano|vegano|"
    r"minha comida|favorit[oa]|meu hobby|hábito|costumo|minha rotina|acordo às|vou dormir|"
    r"meu carro|minha moto|minha placa|"
    r"anote aí|anota aí|lembre-se|lembre que|grave na memória|grave que|não esqueça|"
    r"nunca|sempre que eu|quando eu disser|lembrete permanente"
    r")\b",
    re.IGNORECASE
)


def set_memory_context(user_email: str):
    """Define o e-mail do usuário ativo no contexto da memória de longo prazo."""
    global _MEMORY_USER_EMAIL
    _MEMORY_USER_EMAIL = user_email.strip().lower() if user_email else None


def _get_active_user_email() -> str:
    """Retorna o e-mail do usuário ativo."""
    global _MEMORY_USER_EMAIL
    if _MEMORY_USER_EMAIL:
        return _MEMORY_USER_EMAIL
    env_email = os.getenv("GMAIL_EMAIL") or os.getenv("GMAIL_USER") or "usuario@smarthome.local"
    return env_email.strip().lower()


@tool
def gravar_memoria_longo_prazo(
    fato: str,
    categoria: str = "geral",
    importancia: int = 3,
    contexto: str = ""
) -> str:
    """
    Grava ou consolida um fato valioso, aprendizado, hábito, preferência, decisão ou instrução do usuário
    na sua memória de longo prazo persistente para uso futuro.

    Parâmetros:
    - fato: A declaração clara e concisa do fato ou aprendizado a ser lembrado (ex: "O usuário prefere café sem açúcar", "O filho do usuário se chama Lucas", "O usuário acorda sempre às 6h para treinar", "O usuário não gosta de ser interrompido nas quartas à tarde").
    - categoria: Categoria do fato ('preferencia', 'habito', 'rotina', 'pessoal', 'trabalho', 'familiar', 'decisao', 'instrucao', 'geral').
    - importancia: Nível de relevância de 1 (baixo/detalhe) a 5 (crítico/regra fundamental). Padrão: 3.
    - contexto: (Opcional) Contexto ou motivo em que o fato foi mencionado pelo usuário.
    """
    user_email = _get_active_user_email()
    clean_fact = (fato or "").strip()

    if not clean_fact:
        return "Erro: O fato a ser memorizado não pode estar vazio."

    system_logger.info(f"[MemoryTool] Gravando memória para {user_email}: '{clean_fact}' [Cat: {categoria}, Imp: {importancia}]")

    res = db_save_agent_memory(
        user_email=user_email,
        fact=clean_fact,
        category=categoria,
        importance=importancia,
        context=contexto
    )

    if res.get("status") == "created":
        return f"Memória gravada com sucesso! [ID #{res['id']}]: '{clean_fact}' (Categoria: {res['category']}, Importância: {res['importance']}/5)."
    elif res.get("status") == "updated":
        return f"Memória já existente foi atualizada e reforçada! [ID #{res['id']}]: '{clean_fact}' (Importância: {res['importance']}/5)."
    else:
        return f"Erro ao gravar memória: {res.get('message', 'Falha desconhecida')}"


@tool
def consultar_memorias_longo_prazo(
    termo_busca: str = "",
    categoria: str = ""
) -> str:
    """
    Pesquisa e recupera memórias, fatos e aprendizados passados gravados sobre o usuário no banco de dados.

    Parâmetros:
    - termo_busca: (Opcional) Palavra-chave ou assunto para buscar nas memórias (ex: "café", "Lucas", "treino", "rotina"). Se vazio, retorna as memórias mais importantes.
    - categoria: (Opcional) Filtrar por categoria ('preferencia', 'habito', 'rotina', 'pessoal', 'trabalho', 'familiar', 'decisao', 'instrucao').
    """
    user_email = _get_active_user_email()
    memories = db_search_agent_memories(
        user_email=user_email,
        query=termo_busca,
        category=categoria,
        limit=20
    )

    if not memories:
        if termo_busca:
            return f"Nenhuma memória encontrada sobre '{termo_busca}'."
        return "Nenhuma memória de longo prazo gravada ainda para este usuário."

    output = []
    for m in memories:
        cat = m.get("category", "geral")
        fact = m.get("fact", "")
        m_id = m.get("id")
        output.append(f"Memória #{m_id} ({cat}): {fact}")

    return "\n".join(output)


@tool
def listar_todas_memorias() -> str:
    """
    Lista todas as memórias e aprendizados consolidados gravados na base de conhecimento sobre o usuário.
    Use quando o usuário perguntar o que você sabe sobre ele ou pedir para listar o que você lembra.
    """
    user_email = _get_active_user_email()
    memories = db_get_all_agent_memories(user_email=user_email, limit=50)

    if not memories:
        return "Você ainda não possui memórias de longo prazo gravadas sobre este usuário."

    output = []
    for m in memories:
        cat = m.get("category", "geral")
        fact = m.get("fact", "")
        m_id = m.get("id")
        output.append(f"Memória #{m_id} ({cat}): {fact}")

    return "\n".join(output)


@tool
def esquecer_memoria(memoria_id: int) -> str:
    """
    Exclui ou remove uma memória de longo prazo obsoleta, incorreta ou que o usuário solicitou para esquecer.

    Parâmetros:
    - memoria_id: O número identificador ID da memória a ser excluída (ex: 1, 2, 5).
    """
    user_email = _get_active_user_email()
    try:
        m_id_int = int(memoria_id)
    except (ValueError, TypeError):
        return "Erro: O ID da memória deve ser um número inteiro válido."

    system_logger.info(f"[MemoryTool] Excluindo memória #{m_id_int} para {user_email}")
    success = db_delete_agent_memory(user_email=user_email, memory_id=m_id_int)

    if success:
        return f"Memória #{m_id_int} foi esquecida e removida com sucesso do banco de dados."
    else:
        return f"Não foi possível encontrar a memória #{m_id_int} para exclusão."


# =========================================================================
# MOTOR DE APRENDIZADO CONTÍNUO EM SEGUNDO PLANO (BACKGROUND DAEMON THREAD)
# =========================================================================

def _extract_and_save_memories_sync(
    user_message: str,
    agent_response: str,
    user_email: str,
    api_key: str,
    model_name: str = "gemini-2.5-flash-lite"
):
    """
    Executa a extração estruturada de memórias e fatos em segundo plano utilizando LLM.
    Esta função roda dentro de uma daemon thread e nunca bloqueia a resposta ao usuário.
    """
    if not user_message or not user_email or not api_key:
        return

    try:
        from langchain_core.messages import SystemMessage, HumanMessage
        try:
            from api.agent import get_chat_model, get_fallback_models
        except ImportError:
            from agent import get_chat_model, get_fallback_models

        prompt_extract = (
            "Você é um extrator semântico de memória de longo prazo para um assistente residencial.\n"
            "Analise a mensagem do usuário (e a resposta do assistente como contexto).\n"
            "Identifique se o usuário revelou algum fato duradouro, preferência, hábito, rotina, dado pessoal relevante, restrição de saúde ou instrução explícita sobre si mesmo ou sua residência que valha a pena memorizar para o futuro.\n\n"
            "Regras:\n"
            "1. NÃO extraia comandos passageiros ou efêmeros (ex: ligar luz, que horas são, tocar música, abrir site, previsão do tempo).\n"
            "2. Extraia apenas fatos consistentes e duradouros em português claro na 3ª pessoa (ex: 'O usuário torce para o Flamengo', 'O usuário tem preferência por café sem açúcar', 'O usuário é alérgico a camarão').\n"
            "3. Se houver fatos relevantes, retorne APENAS um JSON válido como lista de objetos no seguinte formato:\n"
            '[{"fact": "declaração clara do fato", "category": "preferencia|habito|rotina|pessoal|trabalho|familiar|decisao|instrucao|geral", "importance": 1-5, "context": "motivo ou contexto breve"}]\n'
            "4. Se NÃO houver nenhum fato duradouro a memorizar, retorne APENAS: []\n"
            "5. Não inclua blocos markdown como ```json, responda apenas o texto do JSON puro."
        )

        user_content = f"MENSAGEM DO USUÁRIO: {user_message}\nRESPOSTA DO ASSISTENTE: {agent_response}"

        candidate_models = get_fallback_models(model_name)
        extracted_text = ""
        for m_cand in candidate_models:
            try:
                llm = get_chat_model(m_cand, api_key)
                res = llm.invoke([
                    SystemMessage(content=prompt_extract),
                    HumanMessage(content=user_content)
                ])
                raw_out = getattr(res, "content", str(res))
                if isinstance(raw_out, list) and raw_out:
                    extracted_text = raw_out[0].get("text", str(raw_out)) if isinstance(raw_out[0], dict) else str(raw_out)
                else:
                    extracted_text = str(raw_out)
                break
            except Exception as cand_err:
                system_logger.warning(f"[BackgroundMemory] Modelo {m_cand} falhou na extração de memória: {cand_err}")
                continue

        if not extracted_text:
            return

        # Limpa formatação markdown se houver
        clean_json_str = extracted_text.strip()
        if clean_json_str.startswith("```json"):
            clean_json_str = clean_json_str[7:]
        if clean_json_str.startswith("```"):
            clean_json_str = clean_json_str[3:]
        if clean_json_str.endswith("```"):
            clean_json_str = clean_json_str[:-3]
        clean_json_str = clean_json_str.strip()

        if clean_json_str == "[]" or not clean_json_str:
            return

        facts_list = json.loads(clean_json_str)
        if not isinstance(facts_list, list):
            return

        for item in facts_list:
            if isinstance(item, dict) and item.get("fact"):
                fact = str(item["fact"]).strip()
                cat = str(item.get("category", "geral")).strip().lower()
                imp = int(item.get("importance", 3))
                ctx = str(item.get("context", user_message[:100])).strip()

                save_res = db_save_agent_memory(
                    user_email=user_email,
                    fact=fact,
                    category=cat,
                    importance=imp,
                    context=ctx
                )
                system_logger.info(
                    f"[BackgroundMemory] Aprendizado contínuo gravou memória com sucesso para {user_email}: "
                    f"'{fact}' [{cat}, imp {imp}/5] (status: {save_res.get('status')})"
                )

    except Exception as e:
        system_logger.error(f"[BackgroundMemory] Erro ao extrair memórias em background: {e}")


def trigger_background_continuous_learning(
    user_message: str,
    agent_response: str,
    user_email: str,
    api_key: str,
    model_name: str = "gemini-2.5-flash-lite"
) -> bool:
    """
    Dispara o aprendizado contínuo e extração de fatos em uma thread separada (background daemon),
    garantindo tempo de resposta zero para o usuário no fluxo principal da conversa.
    """
    if not user_message or not user_email or not api_key:
        return False

    msg_clean = user_message.strip()
    if not msg_clean:
        return False

    # Filtro heurístico rápido via regex para evitar overhead e chamadas de LLM desnecessárias em comandos rotineiros
    if not LEARNING_INDICATORS_REGEX.search(msg_clean):
        return False

    try:
        t = threading.Thread(
            target=_extract_and_save_memories_sync,
            args=(msg_clean, agent_response, user_email, api_key, model_name),
            daemon=True,
            name=f"bg-memory-learn-{user_email[:10]}"
        )
        t.start()
        return True
    except Exception as e:
        system_logger.warning(f"[BackgroundMemory] Falha ao iniciar thread de aprendizado: {e}")
        return False

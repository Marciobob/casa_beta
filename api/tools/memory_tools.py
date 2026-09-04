"""
Ferramentas LangChain para Memória de Longo Prazo e Aprendizado Autônomo do Agente.
Permite ao assistente de IA decidir ativamente e gravar fatos valiosos sobre o usuário,
preferências, hábitos, rotinas, instruções e contexto histórico, além de consultar e gerenciar essas memórias.
"""

import os
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

    output = [f"=== MEMÓRIAS ENCONTRADAS ({len(memories)}) ==="]
    for m in memories:
        imp_stars = "⭐" * m.get("importance", 3)
        cat = m.get("category", "geral")
        fact = m.get("fact", "")
        m_id = m.get("id")
        output.append(f"• [ID #{m_id}] [{cat.upper()}] {imp_stars}: {fact}")
        if m.get("context"):
            output.append(f"  Contexto: {m['context']}")

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

    output = [f"=== TODAS AS MEMÓRIAS CONSOLIDADAS ({len(memories)}) ==="]
    for m in memories:
        imp_stars = "⭐" * m.get("importance", 3)
        cat = m.get("category", "geral")
        fact = m.get("fact", "")
        m_id = m.get("id")
        output.append(f"• #{m_id} [{cat}] {imp_stars} - {fact}")

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

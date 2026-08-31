"""
Ferramentas LangChain para gerenciamento de Notas, Ideias e Listas de Compras (Google Keep / Notes).
Permite criar notas de texto, listas de compras com caixas de seleção, adicionar itens por voz,
marcar itens comprados, ler listas pendentes e pesquisar anotações.
"""

import os
import re
from typing import List, Dict, Any, Optional
from langchain_core.tools import tool

try:
    from api.logger import keep_logger
    from api.database import (
        db_create_note,
        db_get_notes,
        db_get_note_by_id_or_title,
        db_add_items_to_note,
        db_toggle_note_item,
        db_delete_note,
        db_search_notes,
        db_get_notes_count
    )
except ImportError:
    from logger import keep_logger
    from database import (
        db_create_note,
        db_get_notes,
        db_get_note_by_id_or_title,
        db_add_items_to_note,
        db_toggle_note_item,
        db_delete_note,
        db_search_notes,
        db_get_notes_count
    )

_KEEP_USER_EMAIL: Optional[str] = None


def set_keep_context(user_email: str):
    """Define o e-mail do usuário ativo no contexto de notas."""
    global _KEEP_USER_EMAIL
    _KEEP_USER_EMAIL = user_email.strip().lower() if user_email else None


def _get_active_user_email() -> str:
    """Retorna o e-mail do usuário ativo."""
    global _KEEP_USER_EMAIL
    if _KEEP_USER_EMAIL:
        return _KEEP_USER_EMAIL
    env_email = os.getenv("GMAIL_EMAIL") or os.getenv("GMAIL_USER") or "usuario@smarthome.local"
    return env_email.strip().lower()


def _parse_items_string(items_str: str) -> List[str]:
    """Divide strings com múltiplos itens separados por vírgula, 'e', ';' ou quebras de linha."""
    if not items_str:
        return []
    # Substitui conjunção ' e ' por vírgula para facilitar divisão
    cleaned = re.sub(r"\s+e\s+", ", ", items_str, flags=re.IGNORECASE)
    parts = re.split(r"[,;\n\r]+", cleaned)
    return [p.strip() for p in parts if p.strip()]


def _format_note_summary(n: Dict[str, Any]) -> str:
    """Formata o resumo de uma nota ou lista para voz/texto."""
    pin_icon = "📌 " if n.get("is_pinned") else ""
    if n.get("note_type") == "lista":
        items = n.get("items", [])
        total = len(items)
        pending = sum(1 for it in items if not it.get("is_completed"))
        return f"• {pin_icon}Lista #{n['id']} '{n['title']}': {pending} de {total} itens a comprar"
    else:
        preview = n.get("content", "")
        if len(preview) > 60:
            preview = preview[:57] + "..."
        desc = f" - \"{preview}\"" if preview else ""
        return f"• {pin_icon}Nota #{n['id']} '{n['title']}'{desc}"


def _format_note_details(n: Dict[str, Any]) -> str:
    """Formata os detalhes completos de uma nota ou lista de compras."""
    if n.get("note_type") == "lista":
        items = n.get("items", [])
        if not items:
            return f"A lista '{n['title']}' está vazia no momento."
            
        pending = [it["item_text"] for it in items if not it.get("is_completed")]
        completed = [it["item_text"] for it in items if it.get("is_completed")]
        
        resp_parts = [f"Lista de Compras: '{n['title']}'"]
        if pending:
            resp_parts.append("Itens pendentes a comprar:\n" + "\n".join([f"  ⬜ {p}" for p in pending]))
        else:
            resp_parts.append("Todos os itens já foram comprados/concluídos!")
            
        if completed:
            resp_parts.append("Itens já comprados:\n" + "\n".join([f"  ✅ {c}" for c in completed]))
            
        return "\n\n".join(resp_parts)
    else:
        conteudo = n.get("content") or "Nota sem conteúdo de texto."
        return f"Nota '{n['title']}':\n{conteudo}"


# =========================================================================
# FERRAMENTAS LANGCHAIN (@tool)
# =========================================================================

@tool
def criar_nota(
    titulo: str,
    conteudo: str = "",
    tipo: str = "texto",
    itens: str = "",
    cor: str = "padrao",
    fixada: bool = False
) -> str:
    """Cria uma nova nota de texto ou lista de compras/afazeres com itens.
    Use quando o usuário pedir para criar uma nota, lista de compras, anotação ou registrar uma ideia.
    
    Args:
        titulo: Título da nota ou lista (ex: 'Lista de Compras', 'Ideia de Projeto', 'Lista do Supermercado').
        conteudo: Texto da nota se for uma nota comum de texto (opcional).
        tipo: Tipo da nota ('texto' para anotações livres ou 'lista' para listas de compras com caixas de seleção) (padrão: 'texto').
        itens: Itens da lista separados por vírgula se for do tipo lista (ex: 'leite, café, pão, queijo, ovos').
        cor: Cor visual da nota (ex: 'amarelo', 'verde', 'azul', 'vermelho', 'padrao').
        fixada: Se a nota deve ser fixada no topo (opcional).
    """
    user_email = _get_active_user_email()
    keep_logger.info(f"Criando nota: '{titulo}' | tipo: '{tipo}' | itens: '{itens}'")
    
    if not titulo or not titulo.strip():
        return "Erro: O título da nota ou lista não pode estar vazio."
        
    # Auto-detecta tipo lista se o título tiver "compras", "lista" ou se 'itens' forem informados
    is_list = tipo.lower() in ("lista", "checklist", "compras") or bool(itens) or "lista" in titulo.lower() or "compras" in titulo.lower()
    clean_type = "lista" if is_list else "texto"
    
    parsed_items = _parse_items_string(itens) if is_list else []
    
    note = db_create_note(
        user_email=user_email,
        title=titulo.strip(),
        content=conteudo.strip(),
        note_type=clean_type,
        color=cor.strip().lower(),
        is_pinned=fixada,
        items=parsed_items
    )
    
    if clean_type == "lista":
        count = len(parsed_items)
        items_msg = f" com {count} item(ns): {', '.join(parsed_items)}" if count > 0 else " vazia"
        return f"Sucesso: A lista de compras '{note['title']}' foi criada{items_msg}!"
    else:
        return f"Sucesso: A nota '{note['title']}' foi salva com sucesso nas suas anotações!"


@tool
def adicionar_itens_lista(titulo_ou_id: str, novos_itens: str) -> str:
    """Adiciona novos produtos ou itens a uma lista de compras ou notas já existente.
    Use quando o usuário pedir para adicionar itens na lista de compras (ex: 'Adicione manteiga e café na lista de compras').
    
    Args:
        titulo_ou_id: Título ou ID da lista de compras (ex: 'Lista de Compras', 'Supermercado', '1').
        novos_itens: Itens a serem adicionados separados por vírgula ou 'e' (ex: 'manteiga, café, sabonete').
    """
    user_email = _get_active_user_email()
    keep_logger.info(f"Adicionando itens na lista '{titulo_ou_id}': '{novos_itens}'")
    
    if not novos_itens or not novos_itens.strip():
        return "Por favor, informe quais itens deseja adicionar à lista."
        
    parsed = _parse_items_string(novos_itens)
    if not parsed:
        return "Nenhum item válido foi informado para adicionar."
        
    # Tenta atualizar lista existente
    updated = db_add_items_to_note(user_email, titulo_ou_id, parsed)
    if not updated:
        # Se a lista não existir, cria automaticamente!
        list_title = titulo_ou_id.strip() if titulo_ou_id else "Lista de Compras"
        db_create_note(user_email=user_email, title=list_title, note_type="lista", items=parsed)
        return f"A lista '{list_title}' não existia e foi criada com os itens: {', '.join(parsed)}."
        
    return f"Sucesso: Adicionei {len(parsed)} item(ns) ({', '.join(parsed)}) na lista '{updated['title']}'!"


@tool
def marcar_item_lista(titulo_ou_id: str, item_nome: str, concluido: bool = True) -> str:
    """Marca ou desmarca um item da lista de compras como comprado ou concluído.
    Use quando o usuário disser que comprou ou pegou um item do supermercado (ex: 'Já comprei o leite').
    
    Args:
        titulo_ou_id: Título ou ID da lista (ex: 'Lista de Compras', '1').
        item_nome: Nome do produto/item que foi comprado (ex: 'leite', 'café').
        concluido: True para marcar como comprado, False para desmarcar (padrão: True).
    """
    user_email = _get_active_user_email()
    keep_logger.info(f"Marcando item '{item_nome}' na lista '{titulo_ou_id}' como concluido={concluido}")
    
    if not item_nome or not item_nome.strip():
        return "Por favor, informe qual item deseja marcar."
        
    updated = db_toggle_note_item(user_email, titulo_ou_id, item_nome.strip(), is_completed=concluido)
    status_str = "comprado" if concluido else "pendente"
    if updated:
        return f"Perfeito! O item '{item_nome}' foi marcado como {status_str} na lista '{updated['title']}'."
    else:
        return f"Não encontrei o item '{item_nome}' na lista '{titulo_ou_id}'."


@tool
def ler_nota(titulo_ou_id: str) -> str:
    """Lê o conteúdo completo de uma nota ou todos os itens de uma lista de compras.
    Use sempre que o usuário perguntar o que tem na lista de compras ou pedir para ler uma anotação.
    
    Args:
        titulo_ou_id: Título ou ID da nota ou lista (ex: 'Lista de Compras', 'Ideia de App', '1').
    """
    user_email = _get_active_user_email()
    keep_logger.info(f"Lendo nota/lista: '{titulo_ou_id}'")
    
    note = db_get_note_by_id_or_title(user_email, titulo_ou_id)
    if not note:
        # Se procurou por "lista de compras" e não achou com esse nome exato, tenta buscar primeira lista
        if "compras" in titulo_ou_id.lower() or "lista" in titulo_ou_id.lower():
            lists = db_get_notes(user_email, note_type="lista", limit=1)
            if lists:
                return _format_note_details(lists[0])
        return f"Não encontrei nenhuma nota ou lista com o título '{titulo_ou_id}'."
        
    return _format_note_details(note)


@tool
def listar_notas(tipo: str = "todas") -> str:
    """Lista todas as notas, ideias e listas de compras salvas no sistema.
    
    Args:
        tipo: Tipo das notas a listar ('todas', 'lista' para listas de compras ou 'texto' para notas comuns) (padrão: 'todas').
    """
    user_email = _get_active_user_email()
    keep_logger.info(f"Listando notas (tipo='{tipo}')")
    
    notes = db_get_notes(user_email, note_type=tipo, limit=30)
    if not notes:
        if tipo == "lista":
            return "Você não tem nenhuma lista de compras criada no momento."
        return "Você não tem nenhuma nota salva no momento."
        
    items = [_format_note_summary(n) for n in notes]
    header = f"Você tem {len(notes)} nota(s) e lista(s) salvas:"
    return f"{header}\n\n" + "\n".join(items)


@tool
def excluir_nota(titulo_ou_id: str) -> str:
    """Exclui e apaga uma nota ou lista de compras do sistema.
    
    Args:
        titulo_ou_id: Título ou ID da nota ou lista a ser excluída (ex: 'Lista de Compras', '1').
    """
    user_email = _get_active_user_email()
    keep_logger.info(f"Excluindo nota: '{titulo_ou_id}'")
    
    if not titulo_ou_id or not titulo_ou_id.strip():
        return "Por favor, informe o título ou ID da nota que deseja excluir."
        
    deleted = db_delete_note(user_email, titulo_ou_id.strip())
    if deleted:
        return f"Sucesso: A {deleted['note_type']} '{deleted['title']}' foi excluída com sucesso."
    else:
        return f"Não encontrei nenhuma nota ou lista com o título '{titulo_ou_id}' para excluir."


@tool
def buscar_notas(termo: str) -> str:
    """Pesquisa notas e itens de listas por palavras-chave.
    
    Args:
        termo: Termo ou palavra-chave para pesquisar (ex: 'leite', 'projeto', 'supermercado', 'viagem').
    """
    user_email = _get_active_user_email()
    keep_logger.info(f"Buscando notas pelo termo: '{termo}'")
    
    if not termo or not termo.strip():
        return "Por favor, informe a palavra-chave para buscar as notas."
        
    results = db_search_notes(user_email, termo.strip())
    if not results:
        return f"Nenhuma nota ou lista encontrada com o termo '{termo}'."
        
    items = [_format_note_summary(n) for n in results]
    return f"Encontrei {len(results)} nota(s) para '{termo}':\n\n" + "\n".join(items)

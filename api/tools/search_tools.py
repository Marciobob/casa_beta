import warnings
from langchain_core.tools import tool

# Suporte ao pacote ddgs ou duckduckgo_search sem warnings
try:
    from ddgs import DDGS
except ImportError:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            from duckduckgo_search import DDGS
    except ImportError:
        DDGS = None

@tool
def pesquisar_na_internet(consulta: str) -> str:
    """
    Pesquisa informações atualizadas na internet em tempo real.
    Útil para consultar notícias, previsão do tempo, clima, sugestões de filmes, curiosidades, fatos e pesquisas gerais.
    
    Args:
        consulta: Termo ou pergunta a ser pesquisada na internet em português ou inglês.
    """
    if not consulta:
        return "Nenhuma consulta fornecida."
        
    try:
        if DDGS is not None:
            with DDGS() as ddgs:
                results = list(ddgs.text(consulta, max_results=4))
                if results:
                    formatted = []
                    for r in results:
                        formatted.append(f"Título: {r.get('title', '')}\nResumo: {r.get('body', '')}\nLink: {r.get('href', '')}")
                    return "\n\n".join(formatted)
        
        # Fallback simples caso ddgs não esteja disponível
        return f"Resultados para '{consulta}': Não foi possível conectar ao mecanismo de busca no momento."
    except Exception as e:
        return f"Erro ao realizar pesquisa na internet: {str(e)}"

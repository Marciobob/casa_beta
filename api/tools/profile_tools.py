from typing import Dict, Any, Optional

try:
    from langchain_core.tools import tool
except ImportError:
    try:
        from langchain.tools import tool
    except ImportError:
        def tool(func):
            func.name = func.__name__
            func.invoke = lambda args: func(**(args if isinstance(args, dict) else {"tema_ou_pergunta": str(args)}))
            return func

try:
    from api.logger import agent_logger
    from api.database import get_user_profile
except ImportError:
    from logger import agent_logger
    from database import get_user_profile

_current_user_profile = {}
_current_user_email = ""

def set_profile_context(user_email: str = "", profile_data: Optional[Dict[str, Any]] = None):
    """Atualiza a memória de contexto do perfil do usuário para o ciclo atual."""
    global _current_user_profile, _current_user_email
    _current_user_email = user_email or ""
    if profile_data:
        _current_user_profile = dict(profile_data)
    elif user_email:
        _current_user_profile = get_user_profile(user_email)
    else:
        _current_user_profile = {}

@tool
def consultar_perfil_usuario(tema_ou_pergunta: str = "") -> str:
    """
    Consulta a memória e o perfil pessoal do usuário cadastrado no sistema.
    Retorna informações como tipo sanguíneo, carro, comidas favoritas, filmes/séries preferidos, 
    músicas favoritas, passeios e lugares que gosta, alergias, saúde e o panorama geral de sua vida.
    
    Args:
        tema_ou_pergunta: O tema ou pergunta sobre o usuário (ex: 'tipo sanguíneo', 'carro', 'comidas favoritas', 'filmes', 'perfil completo').
    """
    agent_logger.info(f"Tool consultar_perfil_usuario acionada para tema: '{tema_ou_pergunta}'")
    
    if not _current_user_profile:
        return "Nenhum dado de perfil pessoal foi cadastrado para o usuário ainda."
        
    p = _current_user_profile
    resumo_linhas = []
    
    if p.get("blood_type"):
        resumo_linhas.append(f"Tipo Sanguíneo: {p['blood_type']}")
    if p.get("car_info"):
        resumo_linhas.append(f"Carro / Veículo: {p['car_info']}")
    if p.get("favorite_foods"):
        resumo_linhas.append(f"Comidas Favoritas: {p['favorite_foods']}")
    if p.get("favorite_movies"):
        resumo_linhas.append(f"Filmes e Séries Favoritos: {p['favorite_movies']}")
    if p.get("favorite_music"):
        resumo_linhas.append(f"Músicas e Artistas Favoritos: {p['favorite_music']}")
    if p.get("favorite_places"):
        resumo_linhas.append(f"Passeios e Lugares Favoritos: {p['favorite_places']}")
    if p.get("allergies_health"):
        resumo_linhas.append(f"Saúde / Alergias / Observações Médicas: {p['allergies_health']}")
    if p.get("personal_notes"):
        resumo_linhas.append(f"Panorama Geral da Vida e Notas Pessoais: {p['personal_notes']}")
        
    if not resumo_linhas:
        return "O perfil do usuário existe, mas os campos detalhados ainda não foram preenchidos na tela de perfil."
        
    resultado = "Dados do Perfil do Usuário:\n" + "\n".join(resumo_linhas)
    agent_logger.info(f"Retorno do perfil: {resultado}")
    return resultado

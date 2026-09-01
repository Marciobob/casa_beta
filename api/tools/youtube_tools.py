import re
import json
import urllib.request
import urllib.parse
from typing import Optional, List, Dict, Any
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
    from youtube_transcript_api import YouTubeTranscriptApi
except ImportError:
    YouTubeTranscriptApi = None


def extract_video_id(url_or_id: str) -> Optional[str]:
    """Extrai o ID de 11 caracteres de uma URL do YouTube ou valida se a string já é um ID."""
    if not url_or_id:
        return None
    
    clean = url_or_id.strip()
    
    # Se já é um ID de 11 caracteres
    if re.match(r'^[a-zA-Z0-9_-]{11}$', clean):
        return clean
    
    # youtube.com/watch?v=...
    m = re.search(r'(?:v=|\/v\/|embed\/|shorts\/|youtu\.be\/|\/e\/|watch\?v=|\&v=)([a-zA-Z0-9_-]{11})', clean)
    if m:
        return m.group(1)
    
    return None


def search_youtube_videos(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """Pesquisa vídeos no YouTube via scraping leve de resultados públicos, sem necessidade de API key."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept-Language': 'pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7'
    }
    encoded_query = urllib.parse.quote(query)
    url = f"https://www.youtube.com/results?search_query={encoded_query}"
    
    videos = []
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=8) as response:
            html = response.read().decode('utf-8', errors='ignore')
            
        # Tenta extrair do objeto JSON ytInitialData
        match = re.search(r'var ytInitialData = ({.*?});</script>', html)
        if match:
            try:
                data = json.loads(match.group(1))
                contents = data.get('contents', {}).get('twoColumnSearchResultsRenderer', {}).get('primaryContents', {}).get('sectionListRenderer', {}).get('contents', [])
                for section in contents:
                    item_section = section.get('itemSectionRenderer', {})
                    for item in item_section.get('contents', []):
                        v = item.get('videoRenderer')
                        if v and 'videoId' in v:
                            vid = v['videoId']
                            
                            # Título
                            title = ""
                            if 'title' in v:
                                runs = v['title'].get('runs', [])
                                if runs:
                                    title = runs[0].get('text', '')
                                if not title and 'accessibility' in v['title']:
                                    title = v['title']['accessibility'].get('accessibilityData', {}).get('label', '')
                            
                            # Canal
                            channel = ""
                            owner_runs = v.get('ownerText', {}).get('runs', [])
                            if owner_runs:
                                channel = owner_runs[0].get('text', '')
                                
                            # Duração
                            length = v.get('lengthText', {}).get('simpleText', '')
                            
                            videos.append({
                                'id': vid,
                                'title': title or 'Vídeo do YouTube',
                                'channel': channel or 'Canal',
                                'length': length,
                                'url': f"https://www.youtube.com/watch?v={vid}"
                            })
                            if len(videos) >= max_results:
                                break
                    if len(videos) >= max_results:
                        break
            except Exception as err_json:
                agent_logger.warning(f"[YouTubeTools] Falha ao decodificar ytInitialData: {err_json}")
                
        if not videos:
            # Fallback por regex direto no HTML
            ids = list(dict.fromkeys(re.findall(r'\"videoId\":\"([a-zA-Z0-9_-]{11})\"', html)))
            for vid in ids[:max_results]:
                videos.append({
                    'id': vid,
                    'title': 'Vídeo encontrado no YouTube',
                    'channel': '',
                    'length': '',
                    'url': f"https://www.youtube.com/watch?v={vid}"
                })
    except Exception as e:
        agent_logger.error(f"[YouTubeTools] Erro ao pesquisar no YouTube para '{query}': {e}")
        
    return videos


def get_video_transcript(video_id: str, languages: Optional[List[str]] = None) -> Optional[str]:
    """Obtém e formata a transcrição de um vídeo do YouTube."""
    if not YouTubeTranscriptApi:
        return None
        
    langs = languages or ['pt', 'pt-BR', 'en', 'es']
    
    try:
        api = YouTubeTranscriptApi()
        
        # 1. Tenta buscar diretamente nos idiomas preferidos
        try:
            fetched = api.fetch(video_id, languages=langs)
            if fetched and hasattr(fetched, 'snippets') and fetched.snippets:
                text_pieces = [s.text.strip() for s in fetched.snippets if getattr(s, 'text', '').strip()]
                return " ".join(text_pieces)
        except Exception:
            pass
            
        # 2. Tenta listar transcrições disponíveis e traduzir se necessário
        try:
            transcript_list = api.list(video_id)
            # Tenta encontrar manual ou gerada em pt
            target_transcript = None
            try:
                target_transcript = transcript_list.find_transcript(langs)
            except Exception:
                # Pega a primeira disponível e tenta traduzir para português
                for t in transcript_list:
                    try:
                        target_transcript = t.translate('pt')
                        break
                    except Exception:
                        target_transcript = t
                        break
                        
            if target_transcript:
                data = target_transcript.fetch()
                if hasattr(data, 'snippets'):
                    return " ".join([s.text.strip() for s in data.snippets if getattr(s, 'text', '').strip()])
                elif isinstance(data, list):
                    return " ".join([item.get('text', '').strip() for item in data if isinstance(item, dict) and item.get('text')])
        except Exception:
            pass
            
    except Exception as e:
        agent_logger.warning(f"[YouTubeTools] Não foi possível extrair transcrição do vídeo {video_id}: {e}")
        
    return None


@tool
def pesquisar_e_transcrever_youtube(termo_ou_url: str) -> str:
    """
    Pesquisa vídeos e tutoriais no YouTube, extrai a transcrição completa das falas/legendas
    e retorna o conteúdo detalhado para o agente resumir, ensinar o passo a passo ou explicar tutoriais.
    
    Use sempre que o usuário pedir:
    - Tutoriais em vídeo ou passo a passo (ex: 'como arrumar panela de pressão', 'como consertar chuveiro', 'como trocar torneira', 'receita de strogonoff no youtube', 'tutorial de como formatar pc').
    - Pesquisar no YouTube ou ver o que um vídeo ensina.
    - Resumir ou transcrever um link de vídeo do YouTube fornecido.
    
    Args:
        termo_ou_url: Assunto, pergunta do tutorial ou link/URL do vídeo no YouTube.
    """
    if not termo_ou_url or not termo_ou_url.strip():
        return "Por favor, informe o assunto, dúvida ou link do vídeo que deseja pesquisar no YouTube."
        
    query = termo_ou_url.strip()
    agent_logger.info(f"[YouTubeTools] Solicitação recebida: '{query}'")
    
    # 1. Verifica se foi passado um link direto ou ID de vídeo
    direct_id = extract_video_id(query)
    
    if direct_id:
        transcript = get_video_transcript(direct_id)
        video_url = f"https://www.youtube.com/watch?v={direct_id}"
        if transcript:
            # Limita tamanho para não sobrecarregar contexto mantendo os pontos principais
            max_chars = 6000
            truncated_transcript = transcript[:max_chars]
            if len(transcript) > max_chars:
                truncated_transcript += "... [transcrição completa do vídeo continua]"
                
            return (
                f"🎬 VÍDEO DO YOUTUBE ENCONTRADO:\n"
                f"🔗 Link: {video_url}\n\n"
                f"📝 TRANSCRIÇÃO DAS FALAS DO VÍDEO:\n"
                f"\"{truncated_transcript}\"\n\n"
                f"Instrução para a resposta: Resuma com clareza os passos, ensinamentos e instruções descritas na transcrição acima de forma natural em português para o usuário."
            )
        else:
            return (
                f"🎬 VÍDEO DO YOUTUBE: {video_url}\n"
                f"Aviso: Este vídeo específico não possui legendas ou transcrição automática disponíveis no YouTube. "
                f"Informe ao usuário o link do vídeo e dê as orientações gerais sobre o tema."
            )
            
    # 2. Pesquisa vídeos no YouTube sobre o assunto solicitado
    videos = search_youtube_videos(query, max_results=5)
    
    if not videos:
        return (
            f"Não foram encontrados vídeos diretamente no YouTube para a busca: '{query}'. "
            f"Tente reformular a pergunta ou use a ferramenta 'pesquisar_na_internet'."
        )
        
    # 3. Itera sobre os vídeos encontrados até obter uma transcrição válida
    selected_video = None
    transcript_text = None
    
    for v in videos:
        vid_id = v.get("id")
        if not vid_id:
            continue
            
        t = get_video_transcript(vid_id)
        if t and len(t.strip()) > 50:
            selected_video = v
            transcript_text = t
            break
            
    if selected_video and transcript_text:
        max_chars = 6000
        truncated = transcript_text[:max_chars]
        if len(transcript_text) > max_chars:
            truncated += "... [transcrição detalhada do tutorial continua]"
            
        duration_info = f" | Duração: {selected_video.get('length')}" if selected_video.get('length') else ""
        channel_info = f" | Canal: {selected_video.get('channel')}" if selected_video.get('channel') else ""
        
        return (
            f"🎬 VÍDEO TUTORIAL ENCONTRADO NO YOUTUBE:\n"
            f"📌 Título: {selected_video.get('title')}\n"
            f"📺 Informações: {channel_info}{duration_info}\n"
            f"🔗 Link: {selected_video.get('url')}\n\n"
            f"📝 CONTEÚDO EXTRAÍDO DA TRANSCRIÇÃO DO VÍDEO:\n"
            f"\"{truncated}\"\n\n"
            f"Instrução para o Agente: Utilize as informações e o passo a passo da transcrição acima para responder ao usuário com uma explicação clara, prática e estruturada de como resolver o problema ou seguir o tutorial, citando o vídeo e o canal como fonte."
        )
        
    # Caso nenhum dos vídeos tenha transcrição disponível, retorna lista dos vídeos encontrados
    videos_summary = []
    for i, v in enumerate(videos[:3], 1):
        dur = f" ({v.get('length')})" if v.get('length') else ""
        ch = f" por {v.get('channel')}" if v.get('channel') else ""
        videos_summary.append(f"{i}. '{v.get('title')}'{ch}{dur} - Link: {v.get('url')}")
        
    return (
        f"Foram encontrados os seguintes vídeos no YouTube para '{query}', porém nenhum deles possui legendas/transcrição automáticas liberadas para leitura direta:\n\n"
        + "\n".join(videos_summary) +
        f"\n\nInstrução: Explique as orientações gerais sobre '{query}' com base no seu conhecimento e informe os links dos vídeos recomendados acima."
    )

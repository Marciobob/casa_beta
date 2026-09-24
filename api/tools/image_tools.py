import os
import sys
import time
import uuid
import base64
import requests
from pathlib import Path
from typing import Optional, Dict, Any, List

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
        agent_logger = logging.getLogger("IMAGE_TOOLS")

try:
    from api.database import db_get_ai_config
except ImportError:
    try:
        from database import db_get_ai_config
    except ImportError:
        def db_get_ai_config(email: str) -> Dict[str, Any]:
            return {}

# =========================================================================
# CONTEXTO E CONFIGURAÇÃO ATIVA DAS FERRAMENTAS DE IMAGEM
# =========================================================================
_ACTIVE_IMAGE_USER: str = ""
_ACTIVE_IMAGE_API_KEY: str = ""
_ACTIVE_IMAGE_MODEL: str = ""

def set_image_tools_context(user_email: str = "", api_key: str = "", model_name: str = ""):
    """Configura o contexto do usuário para geração de imagens."""
    global _ACTIVE_IMAGE_USER, _ACTIVE_IMAGE_API_KEY, _ACTIVE_IMAGE_MODEL
    _ACTIVE_IMAGE_USER = (user_email or "").strip().lower()
    if api_key:
        _ACTIVE_IMAGE_API_KEY = api_key.strip()
    if model_name:
        _ACTIVE_IMAGE_MODEL = model_name.strip()
    agent_logger.info(f"[ImageTools] Contexto configurado: user='{_ACTIVE_IMAGE_USER}'")

def _get_active_api_key() -> str:
    """Recupera a chave de API Gemini / Google ativa do usuário ou ambiente."""
    if _ACTIVE_IMAGE_API_KEY:
        return _ACTIVE_IMAGE_API_KEY
    if _ACTIVE_IMAGE_USER:
        cfg = db_get_ai_config(_ACTIVE_IMAGE_USER)
        if cfg and cfg.get("api_key"):
            return cfg["api_key"]
    return os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or ""

def _get_output_dir() -> Path:
    """Retorna o diretório local onde as imagens geradas serão salvas."""
    base_dir = Path(__file__).resolve().parent.parent
    static_img_dir = base_dir / "static" / "generated_images"
    static_img_dir.mkdir(parents=True, exist_ok=True)
    return static_img_dir

# =========================================================================
# MAPA DE ESTILOS E MODIFICADORES ARTÍSTICOS
# =========================================================================
STYLE_PROMPT_ENHANCERS: Dict[str, str] = {
    "realista": "hyperrealistic, professional 8k photography, cinematic lighting, 50mm f/1.8 lens, highly detailed, realistic textures, HDR, masterpiece",
    "fotografico": "award-winning studio photography, highly detailed, natural lighting, sharp focus, 8k resolution, cinematic color grading",
    "3d_render": "stunning 3D render, Octane Render, Unreal Engine 5, ray tracing, volumetric lighting, hyperdetailed, 8k wallpaper, CGI masterpiece",
    "arte_digital": "breathtaking digital art, vibrant colors, intricate details, dynamic composition, trending on ArtStation, concept art",
    "anime": "high quality anime key visual, Makoto Shinkai style, vibrant colors, detailed lineart, beautiful lighting, anime aesthetic",
    "ghibli": "Studio Ghibli aesthetic, Hayao Miyazaki inspired, lush vibrant nature, whimsical, soft warm nostalgic lighting, painted background",
    "cyberpunk": "cyberpunk futuristic aesthetic, neon glows, holographic elements, rain reflections, dark sci-fi atmosphere, highly detailed",
    "smart_home": "futuristic luxury smart home interior, IoT automation aesthetics, ambient LED accents, architectural digest photography, clean elegant design",
    "arquitetura": "architectural digest photography, modern contemporary architecture, golden hour sunlight, clean lines, professional exterior and interior",
    "aquarela": "delicate watercolor painting, soft fluid brushstrokes, pastel tones, subtle paper texture, artistic masterpiece",
    "pixel_art": "detailed 16-bit pixel art, vibrant retro game style, clean pixel sprites, nostalgic scene composition, 16-bit masterpiece",
    "logo": "minimalist modern vector logo design, clean geometric iconography, sleek corporate branding, isolated on solid background, flat graphic design",
    "minimalista": "minimalist aesthetic, clean composition, elegant negative space, subtle harmonious color palette, contemporary art",
    "vintage": "vintage retro 1970s 1980s aesthetic, film grain, warm nostalgic tones, Kodachrome analog photography",
    "fantasia": "epic fantasy concept art, matte painting, magical atmosphere, dynamic composition, dramatic lighting, highly detailed",
    "esboco": "fine architectural pencil sketch, detailed cross-hatching, graphite on textured paper, artistic draft"
}

# =========================================================================
# GERADORES ESPECÍFICOS POR MOTOR (IMAGEN 3, OPENAI, FLUX/POLLINATIONS)
# =========================================================================

def _generate_with_google_imagen(prompt: str, aspect_ratio: str = "1:1", api_key: str = "") -> Optional[bytes]:
    """Gera imagem utilizando o Google Imagen 3 via SDK google-genai."""
    try:
        from google import genai
        from google.genai import types

        key = api_key or _get_active_api_key()
        if not key:
            return None

        client = genai.Client(api_key=key)
        # Mapeia proporção válida para o Imagen
        valid_aspects = ["1:1", "3:4", "4:3", "9:16", "16:9"]
        ar = aspect_ratio if aspect_ratio in valid_aspects else "1:1"

        agent_logger.info(f"[ImageTools] Tentando gerar com Google Imagen 3 (aspect_ratio={ar})...")
        
        # Tenta modelos Imagen 3 disponíveis
        for model_name in ["imagen-3.0-generate-002", "imagen-3.0-fast-generate-001", "image-generation-001"]:
            try:
                result = client.models.generate_images(
                    model=model_name,
                    prompt=prompt,
                    config=types.GenerateImagesConfig(
                        number_of_images=1,
                        output_mime_type="image/jpeg",
                        aspect_ratio=ar,
                        person_generation="ALLOW_ADULT",
                        safety_filter_level="BLOCK_MEDIUM_AND_ABOVE",
                    )
                )
                if result and result.generated_images:
                    img_bytes = result.generated_images[0].image.image_bytes
                    if img_bytes and len(img_bytes) > 500:
                        agent_logger.info(f"[ImageTools] Sucesso com Google Imagen 3 ({model_name})!")
                        return img_bytes
            except Exception as model_err:
                agent_logger.warning(f"[ImageTools] Modelo Imagen '{model_name}' falhou: {model_err}")
                continue
    except Exception as e:
        agent_logger.warning(f"[ImageTools] Falha no Google Imagen 3: {e}")
    return None

def _generate_with_openai_dalle(prompt: str, aspect_ratio: str = "1:1") -> Optional[bytes]:
    """Gera imagem utilizando o OpenAI DALL-E 3 caso OPENAI_API_KEY esteja disponível."""
    openai_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not openai_key:
        return None

    try:
        from openai import OpenAI
        client = OpenAI(api_key=openai_key)
        
        size = "1024x1024"
        if aspect_ratio == "16:9":
            size = "1792x1024"
        elif aspect_ratio == "9:16":
            size = "1024x1792"

        agent_logger.info(f"[ImageTools] Tentando gerar com OpenAI DALL-E 3 (size={size})...")
        response = client.images.generate(
            model="dall-e-3",
            prompt=prompt[:950],
            size=size,
            quality="standard",
            n=1
        )
        if response and response.data and response.data[0].url:
            img_url = response.data[0].url
            r = requests.get(img_url, timeout=30)
            if r.status_code == 200 and len(r.content) > 1000:
                agent_logger.info("[ImageTools] Sucesso com OpenAI DALL-E 3!")
                return r.content
    except Exception as e:
        agent_logger.warning(f"[ImageTools] Falha no DALL-E 3: {e}")
    return None

def _generate_with_flux_pollinations(prompt: str, aspect_ratio: str = "1:1") -> Optional[bytes]:
    """Gera imagem com alta velocidade e qualidade através do motor Flux/Pollinations."""
    try:
        # Dimensões de acordo com proporção
        dims = {
            "1:1": (1024, 1024),
            "16:9": (1280, 720),
            "9:16": (720, 1280),
            "4:3": (1024, 768),
            "3:4": (768, 1024)
        }
        w, h = dims.get(aspect_ratio, (1024, 1024))
        
        encoded_prompt = requests.utils.quote(prompt[:800])
        url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width={w}&height={h}&nologo=true&enhance=true&model=flux"
        
        agent_logger.info(f"[ImageTools] Gerando imagem via Flux Engine ({w}x{h})...")
        resp = requests.get(url, timeout=40)
        if resp.status_code == 200 and len(resp.content) > 2000:
            agent_logger.info(f"[ImageTools] Sucesso com Flux Engine ({len(resp.content)} bytes)!")
            return resp.content
    except Exception as e:
        agent_logger.error(f"[ImageTools] Erro no Flux Engine: {e}")
    return None

# =========================================================================
# FERRAMENTAS EXPOSTAS AO AGENTE SEXTA-FEIRA
# =========================================================================

@tool
def gerar_imagem_ia(
    descricao_prompt: str,
    estilo: Optional[str] = "realista",
    proporcao: Optional[str] = "1:1",
    modelo_preferido: Optional[str] = "auto"
) -> str:
    """Gera uma imagem personalizada de alta qualidade com Inteligência Artificial de diversos tipos e estilos visuais.
    
    Argumentos:
    - descricao_prompt: Descrição rica, detalhada e clara do que você quer que a IA crie na imagem (em português ou inglês).
    - estilo: Estilo visual da imagem. Opções:
        * 'realista' ou 'fotografico' -> Fotografia ultra realista de estúdio / cinematográfica.
        * '3d_render' -> Renderização 3D hiper-detalhada em Octane / Unreal Engine 5.
        * 'arte_digital' -> Arte digital moderna e vibrante para papéis de parede e ilustrações.
        * 'anime' -> Estilo de animação japonesa / anime de alta resolução.
        * 'ghibli' -> Estilo nostálgico e mágico do Studio Ghibli (Hayao Miyazaki).
        * 'cyberpunk' -> Iluminação neon futurista, hologramas e clima sci-fi.
        * 'smart_home' -> Ambientes residenciais futuristas e de casas inteligentes com automação.
        * 'arquitetura' -> Projetos de arquitetura, fachadas e design de interiores modernos.
        * 'aquarela' -> Pintura em aquarela fluida e artística.
        * 'pixel_art' -> Arte retrô em pixel art 16-bit.
        * 'logo' -> Logotipo minimalista moderno e vetorizado.
        * 'fantasia' -> Concept art épica de fantasia e mundos mágicos.
        * 'esboco' -> Desenho técnico ou artístico a lápis/grafite.
    - proporcao: Formato da imagem ('1:1' quadrado, '16:9' paisagem/widescreen, '9:16' vertical/stories, '4:3', '3:4').
    - modelo_preferido: 'auto' (escolha inteligente automática), 'imagen3' (Google Imagen 3), 'dalle3' (OpenAI DALL-E 3), 'flux' (Flux AI Engine).
    
    Retorna a URL local da imagem gerada, a tag Markdown pronta para visualização no chat e detalhes da criação.
    """
    if not descricao_prompt or not descricao_prompt.strip():
        return "Erro: Por favor, forneça uma descrição detalhada do que deseja que a IA desenhe na imagem."

    prompt_clean = descricao_prompt.strip()
    estilo_norm = (estilo or "realista").strip().lower().replace(" ", "_").replace("-", "_")
    proporcao_norm = (proporcao or "1:1").strip()
    if proporcao_norm not in ["1:1", "16:9", "9:16", "4:3", "3:4"]:
        proporcao_norm = "1:1"

    # Constrói o prompt enriquecido com modificadores de estilo
    enhancer = STYLE_PROMPT_ENHANCERS.get(estilo_norm, STYLE_PROMPT_ENHANCERS["realista"])
    final_prompt = f"{prompt_clean}, {enhancer}"

    agent_logger.info(f"[ImageTools] Solicitada geração de imagem: estilo='{estilo_norm}', proporção='{proporcao_norm}', prompt='{prompt_clean[:60]}...'")

    img_bytes = None
    engine_used = ""
    model_pref = (modelo_preferido or "auto").strip().lower()

    # 1. Se o usuário pediu Google Imagen 3 ou 'auto'
    if model_pref in ["imagen3", "google", "auto"]:
        img_bytes = _generate_with_google_imagen(final_prompt, aspect_ratio=proporcao_norm)
        if img_bytes:
            engine_used = "Google Imagen 3"

    # 2. Se falhou ou pediu DALL-E 3
    if not img_bytes and model_pref in ["dalle3", "openai", "auto"]:
        img_bytes = _generate_with_openai_dalle(final_prompt, aspect_ratio=proporcao_norm)
        if img_bytes:
            engine_used = "OpenAI DALL-E 3"

    # 3. Fallback de alta fidelidade Flux Engine
    if not img_bytes:
        img_bytes = _generate_with_flux_pollinations(final_prompt, aspect_ratio=proporcao_norm)
        if img_bytes:
            engine_used = "Flux AI Engine"

    if not img_bytes:
        return "Não foi possível gerar a imagem no momento devido a uma instabilidade nos provedores de imagem. Por favor, tente novamente em instantes."

    # Salva o arquivo localmente no diretório estático
    timestamp_str = time.strftime("%Y%m%d_%H%M%S")
    unique_id = uuid.uuid4().hex[:6]
    file_name = f"ai_img_{timestamp_str}_{unique_id}.jpg"
    
    out_dir = _get_output_dir()
    file_path = out_dir / file_name
    
    # Também salva na pasta raiz static se diferente
    try:
        with open(file_path, "wb") as f:
            f.write(img_bytes)
    except Exception as save_err:
        agent_logger.error(f"[ImageTools] Falha ao salvar imagem em disco: {save_err}")
        return f"Erro ao salvar a imagem gerada: {save_err}"

    # Garante espelhamento se a pasta static do frontend for separada
    try:
        alt_dir = Path(__file__).resolve().parent.parent / "static" / "generated_images"
        if alt_dir.resolve() != out_dir.resolve():
            alt_dir.mkdir(parents=True, exist_ok=True)
            with open(alt_dir / file_name, "wb") as f_alt:
                f_alt.write(img_bytes)
    except Exception:
        pass

    image_url = f"/static/generated_images/{file_name}"
    
    res = f"🎨 **Imagem Criada com Sucesso!**\n\n"
    res += f"![{prompt_clean}]({image_url})\n\n"
    res += f"- **Descrição:** {prompt_clean}\n"
    res += f"- **Estilo Aplicado:** `{estilo_norm.title().replace('_', ' ')}`\n"
    res += f"- **Proporção:** `{proporcao_norm}`\n"
    res += f"- **Motor Utilizado:** `{engine_used}`\n"
    res += f"- **Link Direto:** [Abrir Imagem em Alta Resolução]({image_url})"
    
    return res


@tool
def listar_estilos_imagem() -> str:
    """Lista todos os estilos visuais e tipos de imagem disponíveis que o agente pode gerar para o usuário."""
    txt = "🎨 **Estilos Visuais e Tipos de Imagem Disponíveis para Criação:**\n\n"
    for st_name, desc in STYLE_PROMPT_ENHANCERS.items():
        txt += f"• **`{st_name}`**: {desc.split(',')[0].title()} (ex: '{st_name.replace('_', ' ')}')\n"
    
    txt += "\n📐 **Formatos / Proporções Suportadas:**\n"
    txt += "• `1:1` -> Quadrado padrão (ideal para avatares, logos e posts)\n"
    txt += "• `16:9` -> Widescreen / Paisagem (ideal para papéis de parede e banners)\n"
    txt += "• `9:16` -> Vertical (ideal para telas de celular, stories e posters)\n"
    txt += "• `4:3` e `3:4` -> Formatos clássicos fotográficos\n\n"
    txt += "💡 *Dica: Peça algo como 'Crie uma imagem de uma casa inteligente futurista em estilo cyberpunk' ou 'Gere uma pintura em aquarela de um gato no jardim na proporção 16:9'.*"
    return txt

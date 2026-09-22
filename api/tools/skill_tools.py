import os
import re
import json
import zipfile
import io
from typing import Dict, Any, List, Optional, Tuple

try:
    import yaml
except ImportError:
    yaml = None

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
    from api.database import (
        db_list_user_skills,
        db_get_skill_by_slug,
        db_create_skill,
        db_update_skill,
        db_toggle_skill,
        db_get_active_skills_prompt_block,
        _generate_skill_slug
    )
except ImportError:
    from logger import agent_logger
    from database import (
        db_list_user_skills,
        db_get_skill_by_slug,
        db_create_skill,
        db_update_skill,
        db_toggle_skill,
        db_get_active_skills_prompt_block,
        _generate_skill_slug
    )

_current_user_email = ""

def set_skills_context(user_email: str = ""):
    """Define o e-mail do usuário no contexto das tools de skills."""
    global _current_user_email
    _current_user_email = (user_email or "").strip().lower()

def _parse_frontmatter_fallback(text: str) -> Tuple[Dict[str, Any], str]:
    """Extrai metadados YAML simples e o corpo de um arquivo Markdown sem depender do PyYAML."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text

    meta = {}
    body_lines = []
    in_frontmatter = True
    current_list_key = None

    for i in range(1, len(lines)):
        line = lines[i]
        if in_frontmatter:
            if line.strip() == "---":
                in_frontmatter = False
                continue
            
            # Checa se é item de lista
            list_match = re.match(r'^\s*-\s+(.*)$', line)
            if list_match and current_list_key:
                val = list_match.group(1).strip().strip('"\'')
                if isinstance(meta.get(current_list_key), list):
                    meta[current_list_key].append(val)
                continue
            
            # Checa chave: valor
            kv_match = re.match(r'^([a-zA-Z0-9_\-]+)\s*:\s*(.*)$', line)
            if kv_match:
                key = kv_match.group(1).strip().lower()
                val = kv_match.group(2).strip()
                if not val:
                    # Início de lista ou bloco
                    meta[key] = []
                    current_list_key = key
                else:
                    current_list_key = None
                    # Trata JSON inline no yaml (ex: triggers: ["a", "b"])
                    if val.startswith("[") and val.endswith("]"):
                        try:
                            meta[key] = json.loads(val)
                        except Exception:
                            items = [x.strip().strip('"\'') for x in val[1:-1].split(',') if x.strip()]
                            meta[key] = items
                    elif val.lower() in ("true", "yes", "on"):
                        meta[key] = True
                    elif val.lower() in ("false", "no", "off"):
                        meta[key] = False
                    else:
                        meta[key] = val.strip('"\'')
        else:
            body_lines.append(line)

    body = "\n".join(body_lines).strip()
    return meta, body

def parse_skill_markdown(content: str, default_filename: str = "") -> Dict[str, Any]:
    """
    Interpreta um arquivo Markdown de Skill (estilo Claude / Antigravity SKILL.md).
    Suporta YAML frontmatter + corpo de instruções em Markdown.
    """
    raw = content.strip()
    meta = {}
    body = raw

    if raw.startswith("---"):
        if yaml:
            try:
                parts = raw.split("---", 2)
                if len(parts) >= 3:
                    parsed = yaml.safe_load(parts[1])
                    if isinstance(parsed, dict):
                        meta = parsed
                        body = parts[2].strip()
            except Exception as e:
                agent_logger.warning(f"Erro ao usar PyYAML, recorrendo ao fallback: {e}")
                meta, body = _parse_frontmatter_fallback(raw)
        else:
            meta, body = _parse_frontmatter_fallback(raw)
    else:
        # Se não houver frontmatter, tenta extrair título H1
        h1_match = re.search(r'^#\s+(.+)$', raw, flags=re.MULTILINE)
        if h1_match:
            meta["name"] = h1_match.group(1).strip()
            body = raw

    name = meta.get("name") or meta.get("title")
    if not name and default_filename:
        name = os.path.splitext(os.path.basename(default_filename))[0].replace("_", " ").replace("-", " ").title()
    name = name or "Nova Skill Customizada"

    slug = meta.get("slug") or _generate_skill_slug(name)
    description = meta.get("description") or meta.get("summary") or ""
    category = meta.get("category") or "general"
    icon = meta.get("icon") or "⚡"
    
    triggers = meta.get("triggers") or []
    if isinstance(triggers, str):
        triggers = [t.strip() for t in triggers.split(",") if t.strip()]
        
    examples = meta.get("examples") or []
    if isinstance(examples, str):
        examples = [e.strip() for e in examples.split("\n") if e.strip()]

    tools = meta.get("tools") or meta.get("tools_required") or []
    if isinstance(tools, str):
        tools = [t.strip() for t in tools.split(",") if t.strip()]

    return {
        "name": name,
        "slug": slug,
        "description": description,
        "category": category,
        "icon": icon,
        "is_active": meta.get("is_active", True),
        "system_instructions": body,
        "triggers": triggers,
        "examples": examples,
        "tools_required": tools,
        "author": meta.get("author", "user"),
        "version": str(meta.get("version", "1.0.0"))
    }

def parse_skill_json(content: str) -> List[Dict[str, Any]]:
    """Interpreta arquivo JSON com uma ou várias definições de skills."""
    data = json.loads(content)
    if isinstance(data, dict):
        items = [data]
    elif isinstance(data, list):
        items = data
    else:
        return []

    parsed_list = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = item.get("name") or "Skill Importada"
        slug = item.get("slug") or _generate_skill_slug(name)
        instructions = item.get("system_instructions") or item.get("instructions") or item.get("prompt") or ""
        
        triggers = item.get("triggers") or []
        if isinstance(triggers, str):
            triggers = [t.strip() for t in triggers.split(",") if t.strip()]
            
        examples = item.get("examples") or []
        tools = item.get("tools_required") or item.get("tools") or []

        parsed_list.append({
            "name": name,
            "slug": slug,
            "description": item.get("description") or "",
            "category": item.get("category") or "general",
            "icon": item.get("icon") or "⚡",
            "is_active": item.get("is_active", True),
            "system_instructions": instructions,
            "triggers": triggers,
            "examples": examples,
            "tools_required": tools,
            "author": item.get("author", "imported"),
            "version": str(item.get("version", "1.0.0"))
        })
    return parsed_list

def parse_skill_file_content(filename: str, content_bytes: bytes) -> List[Dict[str, Any]]:
    """
    Parser polimórfico universal de arquivos de skills.
    Aceita: .md, .markdown, SKILL.md, .json, .txt e pacotes comprimidos .zip.
    """
    lower_fn = filename.lower()
    results = []

    # 1. Arquivos Compactados (.zip)
    if lower_fn.endswith(".zip"):
        with zipfile.ZipFile(io.BytesIO(content_bytes)) as zf:
            for member in zf.infolist():
                if member.is_dir() or member.filename.startswith("__MACOSX"):
                    continue
                sub_fn = member.filename
                sub_bytes = zf.read(member)
                sub_res = parse_skill_file_content(sub_fn, sub_bytes)
                results.extend(sub_res)
        return results

    # Decodifica texto
    text_content = ""
    for enc in ["utf-8", "latin-1", "cp1252"]:
        try:
            text_content = content_bytes.decode(enc)
            break
        except Exception:
            continue

    if not text_content:
        return []

    # 2. Arquivos JSON (.json)
    if lower_fn.endswith(".json"):
        try:
            return parse_skill_json(text_content)
        except Exception as e:
            agent_logger.error(f"Erro ao parsear JSON de skill '{filename}': {e}")
            return []

    # 3. Arquivos Markdown (.md, .markdown, SKILL.md)
    if lower_fn.endswith(".md") or lower_fn.endswith(".markdown") or "skill" in lower_fn:
        return [parse_skill_markdown(text_content, default_filename=filename)]

    # 4. Arquivos de Texto (.txt)
    lines = [l.strip() for l in text_content.splitlines() if l.strip()]
    name = lines[0] if lines else "Skill Importada"
    body = "\n".join(lines[1:]) if len(lines) > 1 else text_content
    results.append({
        "name": name,
        "slug": _generate_skill_slug(name),
        "description": f"Skill importada a partir de {filename}",
        "category": "general",
        "icon": "⚡",
        "is_active": True,
        "system_instructions": body,
        "triggers": [],
        "examples": [],
        "tools_required": [],
        "author": "user",
        "version": "1.0.0"
    })
    return results

def export_skill_to_markdown(skill: Dict[str, Any]) -> str:
    """Exporta uma skill para formato Claude/AGY SKILL.md com YAML frontmatter."""
    name = skill.get("name", "Skill")
    slug = skill.get("slug", "")
    desc = skill.get("description", "")
    cat = skill.get("category", "general")
    icon = skill.get("icon", "⚡")
    triggers = skill.get("triggers") or []
    tools = skill.get("tools_required") or []
    examples = skill.get("examples") or []
    instructions = skill.get("system_instructions", "").strip()

    triggers_yaml = "\n".join(f"  - {t}" for t in triggers) if triggers else "  []"
    tools_yaml = "\n".join(f"  - {t}" for t in tools) if tools else "  []"
    
    header = f"""---
name: {name}
slug: {slug}
description: "{desc}"
category: {cat}
icon: "{icon}"
version: "{skill.get('version', '1.0.0')}"
author: "{skill.get('author', 'user')}"
triggers:
{triggers_yaml}
tools_required:
{tools_yaml}
---

{instructions}
"""
    return header.strip() + "\n"

# =========================================================================
# LANGCHAIN TOOLS DE SKILLS (AGENTE AUTÔNOMO)
# =========================================================================

@tool
def consultar_skills_ativas(filtro_categoria: str = "") -> str:
    """
    Consulta a lista de habilidades especializadas (Skills) ativas no perfil do usuário.
    Retorna as skills disponíveis, categorias, ícones e um resumo do comportamento especializado.
    
    Args:
        filtro_categoria: Opcional. Filtra por categoria específica (ex: 'desenvolvimento', 'automacao', 'seguranca', 'produtividade', 'comunicacao').
    """
    email = _current_user_email
    if not email:
        return "Nenhum usuário ativo identificado para consulta de skills."

    agent_logger.info(f"Tool consultar_skills_ativas executada para: {email} (filtro: '{filtro_categoria}')")
    skills = db_list_user_skills(email, only_active=True, category=filtro_categoria or None)
    
    if not skills:
        return f"Nenhuma skill ativa encontrada para a categoria '{filtro_categoria}'." if filtro_categoria else "Nenhuma skill está ativada no momento no sistema."

    relatorio = [f"⚡ **HABILIDADES ATIVAS DO SISTEMA ({len(skills)})**:"]
    for s in skills:
        trig = ", ".join(s.get("triggers", [])) or "Geral"
        relatorio.append(f"• {s['icon']} **{s['name']}** (`{s['slug']}`) [{s['category']}]:")
        relatorio.append(f"  - Descrição: {s['description']}")
        relatorio.append(f"  - Gatilhos: {trig}")
    
    return "\n".join(relatorio)

@tool
def alternar_status_skill(nome_ou_slug: str, ativar: bool = True) -> str:
    """
    Ativa ou desativa uma habilidade especializada (Skill) do agente.
    Use quando o morador pedir para ativar/desativar uma skill específica por comando de voz ou texto.
    
    Args:
        nome_ou_slug: Nome ou slug identificador da skill (ex: 'dev_python_senior', 'Especialista em Automação', 'osint').
        ativar: True para ligar/ativar a skill, False para desativar.
    """
    email = _current_user_email
    if not email:
        return "Nenhum usuário ativo identificado para alterar status da skill."

    clean_term = (nome_ou_slug or "").strip().lower()
    skills = db_list_user_skills(email)
    
    target_skill = None
    for s in skills:
        if s["slug"].lower() == clean_term or clean_term in s["name"].lower() or clean_term in s["slug"].lower():
            target_skill = s
            break
            
    if not target_skill:
        return f"Não encontrei nenhuma skill correspondente ao termo '{nome_ou_slug}'. Verifique as skills cadastradas no painel de Skills."

    updated = db_toggle_skill(target_skill["id"], email, is_active=ativar)
    status_str = "ativada" if ativar else "desativada"
    agent_logger.info(f"Skill '{target_skill['name']}' foi {status_str} para {email}")
    return f"A habilidade **{target_skill['icon']} {target_skill['name']}** foi **{status_str}** com sucesso!"

@tool
def cadastrar_ou_atualizar_skill(
    nome: str,
    instrucoes: str,
    descricao: str = "",
    categoria: str = "general",
    icone: str = "⚡",
    gatilhos: str = ""
) -> str:
    """
    Cria uma nova habilidade especializada (Skill) para o agente com diretrizes customizadas de comportamento.
    
    Args:
        nome: Nome da nova skill (ex: 'Especialista em Docker', 'Revisor de Contratos').
        instrucoes: Texto detalhado com as diretrizes e instruções de como o agente deve se comportar.
        descricao: Resumo do objetivo da skill.
        categoria: Categoria (ex: 'desenvolvimento', 'produtividade', 'seguranca', 'automacao', 'comunicacao').
        icone: Emoji representativo da skill (ex: '🐳', '📜', '⚡').
        gatilhos: Palavras-chave separadas por vírgula que ativam o contexto da skill.
    """
    email = _current_user_email
    if not email:
        return "Nenhum usuário ativo identificado para criar nova skill."

    trig_list = [t.strip() for t in gatilhos.split(",") if t.strip()] if gatilhos else []
    slug = _generate_skill_slug(nome)
    
    skill_data = {
        "name": nome.strip(),
        "slug": slug,
        "description": descricao.strip(),
        "category": categoria.strip().lower(),
        "icon": icone.strip() or "⚡",
        "is_active": True,
        "system_instructions": instrucoes.strip(),
        "triggers": trig_list,
        "examples": [],
        "tools_required": [],
        "author": "agent_created",
        "version": "1.0.0"
    }
    
    created = db_create_skill(email, skill_data)
    agent_logger.info(f"Nova skill '{nome}' criada autonomamente para {email}")
    return f"Habilidade **{created['icon']} {created['name']}** criada e ativada com sucesso! Você pode gerenciá-la no painel de Skills."

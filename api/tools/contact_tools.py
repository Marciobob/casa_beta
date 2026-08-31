"""
Ferramentas LangChain para integração completa com Google Contatos (Google Contacts) via protocolo CardDAV
com sincronização e persistência no banco de dados SQLite para velocidade instantânea e tolerância a falhas.
"""

import os
import re
import uuid
import time
import unicodedata
import xml.etree.ElementTree as ET
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor
import requests
from langchain_core.tools import tool

try:
    from api.logger import contacts_logger
    from api.database import (
        db_upsert_contact,
        db_get_contacts,
        db_search_contacts,
        db_delete_contact,
        db_get_contacts_count
    )
except ImportError:
    from logger import contacts_logger
    from database import (
        db_upsert_contact,
        db_get_contacts,
        db_search_contacts,
        db_delete_contact,
        db_get_contacts_count
    )

_LAST_SYNC_TIME = 0.0


_ACTIVE_CONTACT_USER: Optional[str] = None
_ACTIVE_CONTACT_PWD: Optional[str] = None


def set_contact_credentials_context(email_user: Optional[str], app_password: Optional[str]):
    """Define as credenciais do Google Contacts para a execução do usuário ativo."""
    global _ACTIVE_CONTACT_USER, _ACTIVE_CONTACT_PWD
    _ACTIVE_CONTACT_USER = (email_user or "").strip() if email_user else None
    _ACTIVE_CONTACT_PWD = (app_password or "").replace(" ", "").strip() if app_password else None


def _get_carddav_credentials():
    """Recupera e valida as credenciais do Google do usuário ativo ou do ambiente."""
    global _ACTIVE_CONTACT_USER, _ACTIVE_CONTACT_PWD
    if _ACTIVE_CONTACT_USER and _ACTIVE_CONTACT_PWD:
        return _ACTIVE_CONTACT_USER, _ACTIVE_CONTACT_PWD
        
    email = os.getenv("GMAIL_EMAIL") or os.getenv("GMAIL_USER") or ""
    pwd = os.getenv("GMAIL_APP_PASSWORD") or os.getenv("GMAIL_PASSWORD") or ""
    
    email = email.strip()
    pwd = pwd.replace(" ", "").strip()
    
    return email, pwd


def _normalize_text(text: str) -> str:
    """Normaliza texto removendo acentos e convertendo para minúsculas."""
    if not text:
        return ""
    return unicodedata.normalize("NFD", text).encode("ascii", "ignore").decode("utf-8").lower().strip()


def _parse_vcard(vcard_text: str, href: str = "") -> Dict[str, Any]:
    """Faz o parse de um payload vCard 3.0 do Google Contacts."""
    contact = {
        "name": "",
        "phones": [],
        "emails": [],
        "notes": "",
        "uid": "",
        "href": href
    }
    
    if not vcard_text:
        return contact
    
    lines = vcard_text.splitlines()
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # FN (Formatted Name)
        if line.startswith("FN:") or line.startswith("FN;"):
            parts = line.split(":", 1)
            if len(parts) == 2 and not contact["name"]:
                contact["name"] = parts[1].strip()
                
        # N (Structured Name) como fallback
        elif line.startswith("N:") or line.startswith("N;"):
            if not contact["name"]:
                parts = line.split(":", 1)
                if len(parts) == 2:
                    name_parts = [p.strip() for p in parts[1].split(";") if p.strip()]
                    name_parts.reverse()
                    contact["name"] = " ".join(name_parts).strip()
                    
        # TEL (Telefones)
        elif "TEL" in line:
            parts = line.split(":", 1)
            if len(parts) == 2:
                phone_num = parts[1].strip()
                if phone_num and phone_num not in contact["phones"]:
                    contact["phones"].append(phone_num)
                    
        # EMAIL
        elif "EMAIL" in line:
            parts = line.split(":", 1)
            if len(parts) == 2:
                email_addr = parts[1].strip()
                if email_addr and email_addr not in contact["emails"]:
                    contact["emails"].append(email_addr)
                    
        # NOTE
        elif line.startswith("NOTE:") or line.startswith("NOTE;"):
            parts = line.split(":", 1)
            if len(parts) == 2:
                contact["notes"] = parts[1].strip()
                
        # UID
        elif line.startswith("UID:") or line.startswith("UID;"):
            parts = line.split(":", 1)
            if len(parts) == 2:
                contact["uid"] = parts[1].strip()

    # Fallback para UID a partir do href
    if not contact["uid"] and href:
        contact["uid"] = href.rstrip("/").split("/")[-1]
        
    return contact


def sync_google_contacts(force: bool = False) -> int:
    """Sincroniza os contatos do Google via CardDAV com o banco de dados SQLite local."""
    global _LAST_SYNC_TIME
    email, pwd = _get_carddav_credentials()
    if not email or not pwd:
        contacts_logger.warning("Credenciais do Google não configuradas para sincronização de contatos.")
        return 0
        
    # Evita sincronizações excessivas dentro de 60 segundos
    if not force and (time.time() - _LAST_SYNC_TIME < 60) and db_get_contacts_count(email) > 0:
        return db_get_contacts_count(email)
        
    base_url = f"https://www.googleapis.com/carddav/v1/principals/{email}/lists/default/"
    xml_body = """<d:propfind xmlns:d="DAV:">
  <d:prop>
    <d:displayname />
    <d:resourcetype />
    <d:getetag />
  </d:prop>
</d:propfind>"""

    try:
        res = requests.request(
            "PROPFIND",
            base_url,
            data=xml_body,
            auth=(email, pwd),
            headers={"Depth": "1", "Content-Type": "application/xml; charset=utf-8"},
            timeout=10
        )
        
        if res.status_code == 429:
            contacts_logger.warning("Google CardDAV atingiu rate-limit (429). Utilizando contatos locais do SQLite.")
            return db_get_contacts_count(email)
            
        if res.status_code not in (200, 207):
            contacts_logger.error(f"Erro no PROPFIND do CardDAV: HTTP {res.status_code}")
            return db_get_contacts_count(email)
            
        root = ET.fromstring(res.text)
        hrefs = []
        for elem in root.findall(".//{DAV:}response"):
            href_elem = elem.find("{DAV:}href")
            if href_elem is not None and href_elem.text:
                href = href_elem.text.strip()
                if href.rstrip("/") != f"/carddav/v1/principals/{email}/lists/default":
                    hrefs.append(href)
                    
        def _fetch_single(href_path):
            contact_url = f"https://www.googleapis.com{href_path}" if href_path.startswith("/") else href_path
            try:
                res_card = requests.get(contact_url, auth=(email, pwd), timeout=6)
                if res_card.status_code == 200:
                    parsed = _parse_vcard(res_card.text, href=contact_url)
                    if parsed["name"] or parsed["phones"] or parsed["emails"]:
                        return parsed
            except Exception:
                pass
            return None

        # Processa em lote paralelo
        synced_count = 0
        with ThreadPoolExecutor(max_workers=10) as executor:
            for parsed in executor.map(_fetch_single, hrefs):
                if parsed:
                    db_upsert_contact(
                        user_email=email,
                        uid=parsed.get("uid") or parsed.get("href"),
                        href=parsed.get("href", ""),
                        name=parsed.get("name", "Sem nome"),
                        phones=";".join(parsed.get("phones", [])),
                        emails=";".join(parsed.get("emails", [])),
                        notes=parsed.get("notes", "")
                    )
                    synced_count += 1
                    
        _LAST_SYNC_TIME = time.time()
        contacts_logger.info(f"Sincronização de contatos concluída: {synced_count} contatos atualizados no SQLite.")
        return synced_count
    except Exception as e:
        contacts_logger.error(f"Falha na sincronização com o Google CardDAV: {e}")
        return db_get_contacts_count(email)


def formatar_contato(c: Dict[str, Any]) -> str:
    """Formata um contato de forma amigável e limpa."""
    nome = c.get("name") or "Sem nome"
    tels = ", ".join(c.get("phones", [])) or "Sem telefone"
    emails = ", ".join(c.get("emails", [])) or "Sem e-mail"
    notas = f" | Notas: {c.get('notes')}" if c.get("notes") else ""
    return f"• {nome}: Telefone: {tels} | E-mail: {emails}{notas}"


# =========================================================================
# FERRAMENTAS LANGCHAIN (@tool)
# =========================================================================

@tool
def buscar_contato(nome_ou_termo: str) -> str:
    """Busca contatos na sua conta do Google Contacts por nome, telefone ou e-mail.
    Use sempre que o usuário perguntar pelo telefone, e-mail ou dados de alguma pessoa.
    
    Args:
        nome_ou_termo: Nome da pessoa ou termo de busca (ex: 'Lucas', 'Samuel', 'doutor', 'marcio').
    """
    contacts_logger.info(f"Buscando contato: '{nome_ou_termo}'")
    email, pwd = _get_carddav_credentials()
    if not email or not pwd:
        return "As credenciais do Google Contacts não estão configuradas no arquivo .env."
        
    term_norm = _normalize_text(nome_ou_termo)
    if not term_norm:
        return "Por favor, informe o nome ou termo para pesquisar o contato."
        
    # Garante que temos contatos no banco
    if db_get_contacts_count(email) == 0:
        sync_google_contacts(force=True)
        
    contacts = db_get_contacts(email, limit=1000)
    matches = []
    for c in contacts:
        name_norm = _normalize_text(c.get("name", ""))
        phones_str = " ".join(c.get("phones", []))
        emails_str = " ".join(c.get("emails", []))
        notes_norm = _normalize_text(c.get("notes", ""))
        
        if (term_norm in name_norm or 
            term_norm in _normalize_text(phones_str) or 
            term_norm in _normalize_text(emails_str) or 
            term_norm in notes_norm):
            matches.append(c)
            
    if not matches:
        return f"Nenhum contato encontrado com o termo '{nome_ou_termo}' na sua agenda do Google."
        
    res_list = [formatar_contato(c) for c in matches]
    return f"Encontrei {len(matches)} contato(s) para '{nome_ou_termo}':\n\n" + "\n".join(res_list)


@tool
def listar_contatos(limite: int = 15) -> str:
    """Lista os contatos salvos na sua agenda do Google Contacts.
    
    Args:
        limite: Quantidade máxima de contatos para exibir (padrão: 15).
    """
    contacts_logger.info(f"Listando contatos (limite={limite})")
    email, pwd = _get_carddav_credentials()
    if not email or not pwd:
        return "As credenciais do Google Contacts não estão configuradas no arquivo .env."
        
    if db_get_contacts_count(email) == 0:
        sync_google_contacts(force=True)
        
    contacts = db_get_contacts(email, limit=limite)
    total = db_get_contacts_count(email)
    if not contacts:
        return "Nenhum contato encontrado na sua agenda do Google."
        
    res_list = [formatar_contato(c) for c in contacts[:limite]]
    return f"Você tem {total} contato(s) cadastrados na sua agenda do Google:\n\n" + "\n".join(res_list)


@tool
def salvar_contato(nome_completo: str, telefone: str = "", email: str = "", notas: str = "") -> str:
    """Cria e salva um novo contato diretamente na sua conta do Google Contacts via CardDAV.
    
    Args:
        nome_completo: Nome completo da pessoa (ex: 'Lucas Almeida').
        telefone: Número de telefone ou celular (ex: '+55 11 98888-7777').
        email: Endereço de e-mail da pessoa (ex: 'lucas@gmail.com').
        notas: Informações adicionais ou anotações sobre o contato (opcional).
    """
    contacts_logger.info(f"Criando contato: '{nome_completo}' (tel={telefone}, email={email})")
    user_email, pwd = _get_carddav_credentials()
    if not user_email or not pwd:
        return "As credenciais do Google Contacts não estão configuradas no arquivo .env."
        
    if not nome_completo or not nome_completo.strip():
        return "Erro: O nome do contato não pode ser vazio."
        
    clean_name = nome_completo.strip()
    uid = "contact_" + uuid.uuid4().hex[:12]
    url = f"https://www.googleapis.com/carddav/v1/principals/{user_email}/lists/default/{uid}"
    
    # Monta vCard 3.0
    vcard_lines = [
        "BEGIN:VCARD",
        "VERSION:3.0",
        f"FN:{clean_name}",
        f"N:;{clean_name};;;",
        f"UID:{uid}"
    ]
    
    if telefone and telefone.strip():
        vcard_lines.append(f"TEL;TYPE=CELL,PREF:{telefone.strip()}")
    if email and email.strip():
        vcard_lines.append(f"EMAIL;TYPE=HOME,PREF:{email.strip()}")
    if notas and notas.strip():
        vcard_lines.append(f"NOTE:{notas.strip()}")
        
    vcard_lines.append("END:VCARD")
    vcard_payload = "\r\n".join(vcard_lines)
    
    try:
        res = requests.put(
            url,
            data=vcard_payload.encode("utf-8"),
            auth=(user_email, pwd),
            headers={"Content-Type": "text/vcard; charset=utf-8"},
            timeout=10
        )
        
        # Salva imediatamente no banco de dados local
        db_upsert_contact(
            user_email=user_email,
            uid=uid,
            href=url,
            name=clean_name,
            phones=telefone.strip(),
            emails=email.strip(),
            notes=notas.strip()
        )
        
        contacts_logger.info(f"Contato '{clean_name}' salvo com sucesso no Google Contacts e SQLite.")
        detalhes = []
        if telefone:
            detalhes.append(f"Telefone: {telefone}")
        if email:
            detalhes.append(f"E-mail: {email}")
        detalhes_str = " | ".join(detalhes) if detalhes else "Sem dados adicionais"
        return f"Sucesso: O contato '{clean_name}' foi salvo na sua agenda do Google! ({detalhes_str})"
    except Exception as e:
        contacts_logger.error(f"Erro na requisição PUT de contato: {e}")
        return f"Erro ao conectar com o Google Contacts: {str(e)}"


@tool
def excluir_contato(nome_ou_termo: str) -> str:
    """Remove e exclui um contato da sua agenda do Google Contacts.
    
    Args:
        nome_ou_termo: Nome ou termo de busca do contato a ser removido (ex: 'Lucas Almeida').
    """
    contacts_logger.info(f"Tentando excluir contato: '{nome_ou_termo}'")
    user_email, pwd = _get_carddav_credentials()
    if not user_email or not pwd:
        return "As credenciais do Google Contacts não estão configuradas no arquivo .env."
        
    term_norm = _normalize_text(nome_ou_termo)
    if not term_norm:
        return "Por favor, informe o nome do contato que deseja excluir."
        
    contacts = db_get_contacts(user_email, limit=1000)
    target = None
    for c in contacts:
        name_norm = _normalize_text(c.get("name", ""))
        if term_norm in name_norm or name_norm == term_norm:
            target = c
            break
            
    if not target:
        return f"Não encontrei nenhum contato com o nome '{nome_ou_termo}' para excluir."
        
    # Remove do servidor CardDAV do Google se tiver href válido
    if target.get("href"):
        try:
            requests.delete(target["href"], auth=(user_email, pwd), timeout=8)
        except Exception as e:
            contacts_logger.warning(f"Aviso ao deletar contato no CardDAV: {e}")
            
    # Remove do banco local SQLite
    db_delete_contact(user_email, target.get("uid") or target.get("href"))
    contacts_logger.info(f"Contato '{target.get('name')}' excluído com sucesso.")
    return f"Sucesso: O contato '{target.get('name')}' foi excluído da sua agenda do Google."

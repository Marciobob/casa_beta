import os
import imaplib
import smtplib
import email
from email.header import decode_header, make_header
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formatdate, parseaddr
import re
from typing import Tuple, Optional, List, Dict, Any

try:
    from langchain_core.tools import tool
except ImportError:
    try:
        from langchain.tools import tool
    except ImportError:
        def tool(func):
            func.name = func.__name__
            func.invoke = lambda args: func(**(args if isinstance(args, dict) else {"consulta": str(args)}))
            return func

try:
    from api.logger import gmail_logger
except ImportError:
    try:
        from logger import gmail_logger
    except ImportError:
        import logging
        gmail_logger = logging.getLogger("GMAIL")

# =========================================================================
# CONFIGURAÇÕES E CONEXÕES GMAIL (IMAP / SMTP)
# =========================================================================

IMAP_SERVER = "imap.gmail.com"
IMAP_PORT = 993
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

_ACTIVE_GMAIL_USER: Optional[str] = None
_ACTIVE_GMAIL_PWD: Optional[str] = None

def set_gmail_credentials_context(email_user: Optional[str], app_password: Optional[str]):
    """Define as credenciais do Gmail para a execução do usuário ativo."""
    global _ACTIVE_GMAIL_USER, _ACTIVE_GMAIL_PWD
    _ACTIVE_GMAIL_USER = (email_user or "").strip() if email_user else None
    _ACTIVE_GMAIL_PWD = (app_password or "").replace(" ", "").strip() if app_password else None

def get_gmail_credentials() -> Tuple[Optional[str], Optional[str]]:
    """
    Recupera as credenciais do Gmail configuradas para o usuário ativo ou faz fallback para o .env.
    Remove espaços automáticos de senhas de aplicativo geradas pelo Google (ex: 'xxxx xxxx xxxx xxxx').
    """
    global _ACTIVE_GMAIL_USER, _ACTIVE_GMAIL_PWD
    if _ACTIVE_GMAIL_USER and _ACTIVE_GMAIL_PWD:
        return _ACTIVE_GMAIL_USER, _ACTIVE_GMAIL_PWD
        
    email_user = os.getenv("GMAIL_EMAIL") or os.getenv("GMAIL_USER")
    app_password = os.getenv("GMAIL_APP_PASSWORD") or os.getenv("GMAIL_PASSWORD")
    
    if email_user:
        email_user = email_user.strip()
    if app_password:
        app_password = app_password.replace(" ", "").strip()
        
    return email_user, app_password

def decode_mime_text(header_val: Optional[str]) -> str:
    """Decodifica cabeçalhos de e-mail codificados em MIME (ex: =?utf-8?B?...?=)."""
    if not header_val:
        return ""
    try:
        decoded_header = decode_header(header_val)
        return str(make_header(decoded_header))
    except Exception:
        return str(header_val)

def extract_plain_text(msg: email.message.Message) -> str:
    """Extrai o corpo em texto puro de uma mensagem MIME (incluindo multipartes)."""
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get("Content-Disposition", ""))
            
            # Ignora anexos
            if "attachment" in content_disposition:
                continue
                
            if content_type == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    try:
                        body = payload.decode(charset, errors="replace")
                    except Exception:
                        body = payload.decode("latin-1", errors="replace")
                    break
            elif content_type == "text/html" and not body:
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    try:
                        html_text = payload.decode(charset, errors="replace")
                    except Exception:
                        html_text = payload.decode("latin-1", errors="replace")
                    # Limpa tags HTML básicas
                    clean_text = re.sub(r'<[^>]+>', ' ', html_text)
                    body = re.sub(r'\s+', ' ', clean_text).strip()
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            try:
                body = payload.decode(charset, errors="replace")
            except Exception:
                body = payload.decode("latin-1", errors="replace")
            if msg.get_content_type() == "text/html":
                clean_text = re.sub(r'<[^>]+>', ' ', body)
                body = re.sub(r'\s+', ' ', clean_text).strip()

    # Limpeza final de espaços excessivos
    body = re.sub(r'\n{3,}', '\n\n', body).strip()
    return body

def connect_imap() -> Tuple[Optional[imaplib.IMAP4_SSL], Optional[str]]:
    """Cria conexão segura SSL com o servidor IMAP do Gmail."""
    user, password = get_gmail_credentials()
    if not user or not password:
        err = (
            "Credenciais do Gmail não configuradas. Configure as variáveis GMAIL_EMAIL "
            "e GMAIL_APP_PASSWORD (senha de aplicativo de 16 dígitos) no arquivo .env."
        )
        gmail_logger.warning(err)
        return None, err
        
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER, IMAP_PORT)
        mail.login(user, password)
        return mail, None
    except imaplib.IMAP4.error as e:
        err = f"Falha na autenticação do Gmail (IMAP): {e}. Verifique se a Senha de Aplicativo de 16 caracteres está correta."
        gmail_logger.error(err)
        return None, err
    except Exception as e:
        err = f"Erro de conexão com o Gmail (IMAP): {e}"
        gmail_logger.error(err)
        return None, err

def connect_smtp() -> Tuple[Optional[smtplib.SMTP], Optional[str]]:
    """Cria conexão segura TLS com o servidor SMTP do Gmail."""
    user, password = get_gmail_credentials()
    if not user or not password:
        err = (
            "Credenciais do Gmail não configuradas. Configure as variáveis GMAIL_EMAIL "
            "e GMAIL_APP_PASSWORD no arquivo .env."
        )
        gmail_logger.warning(err)
        return None, err
        
    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=15)
        server.starttls()
        server.login(user, password)
        return server, None
    except smtplib.SMTPAuthenticationError as e:
        err = f"Falha de autenticação no envio (SMTP): {e}. Verifique sua Senha de Aplicativo do Gmail."
        gmail_logger.error(err)
        return None, err
    except Exception as e:
        err = f"Erro de conexão SMTP com o Gmail: {e}"
        gmail_logger.error(err)
        return None, err

# =========================================================================
# FERRAMENTAS DO AGENTE LANGCHAIN (GMAIL TOOLS)
# =========================================================================

@tool
def ler_emails_recentes(quantidade: int = 5, apenas_nao_lidos: bool = True) -> str:
    """
    Lê e resume os e-mails mais recentes da caixa de entrada do Gmail.
    Informa ID, Remetente, Assunto, Data e uma prévia do conteúdo de cada mensagem.
    
    Args:
        quantidade: Número máximo de e-mails a serem retornados (padrão: 5).
        apenas_nao_lidos: Se True, busca apenas e-mails não lidos. Se False, busca todos os mais recentes.
    """
    gmail_logger.info(f"Executando ler_emails_recentes (qtd={quantidade}, apenas_nao_lidos={apenas_nao_lidos})")
    mail, err = connect_imap()
    if err or not mail:
        return err

    try:
        mail.select("INBOX")
        criterio = "UNSEEN" if apenas_nao_lidos else "ALL"
        status, data = mail.search(None, criterio)
        
        if status != "OK" or not data or not data[0]:
            if apenas_nao_lidos:
                return "Você não possui novos e-mails não lidos no Gmail no momento."
            return "Nenhum e-mail encontrado na sua caixa de entrada do Gmail."
            
        email_ids = data[0].split()
        total_encontrados = len(email_ids)
        # Pega os N mais recentes (últimos da lista)
        selected_ids = email_ids[-quantidade:]
        selected_ids.reverse() # Mais recente primeiro
        
        resultados = []
        for msg_id in selected_ids:
            res, msg_data = mail.fetch(msg_id, "(RFC822)")
            if res != "OK" or not msg_data or not msg_data[0]:
                continue
                
            raw_email = msg_data[0][1]
            msg = email.message_from_bytes(raw_email)
            
            remetente = decode_mime_text(msg.get("From", "Desconhecido"))
            assunto = decode_mime_text(msg.get("Subject", "(Sem Assunto)"))
            data_envio = msg.get("Date", "")
            corpo = extract_plain_text(msg)
            
            # Limita a prévia para não sobrecarregar o prompt
            previa = corpo[:350] + ("..." if len(corpo) > 350 else "") if corpo else "(Sem conteúdo de texto)"
            
            id_str = msg_id.decode("utf-8", errors="ignore")
            resultados.append(
                f"[ID: {id_str}]\n"
                f"Remetente: {remetente}\n"
                f"Assunto: {assunto}\n"
                f"Data: {data_envio}\n"
                f"Conteúdo: {previa}"
            )
            
        mail.close()
        mail.logout()
        
        tipo_str = "não lido(s)" if apenas_nao_lidos else "recente(s)"
        header = f"Encontrei {len(resultados)} e-mail(s) {tipo_str} (de um total de {total_encontrados}):\n\n"
        return header + "\n\n---\n\n".join(resultados)
        
    except Exception as e:
        gmail_logger.error(f"Erro ao ler e-mails: {e}")
        return f"Erro ao acessar e-mails do Gmail: {str(e)}"

@tool
def buscar_emails(termo_busca: str, quantidade: int = 5) -> str:
    """
    Pesquisa e-mails na caixa de entrada do Gmail por remetente, assunto ou palavra-chave.
    
    Args:
        termo_busca: Palavra, assunto ou endereço de e-mail a pesquisar.
        quantidade: Número máximo de e-mails a retornar (padrão: 5).
    """
    if not termo_busca:
        return "Informe um termo ou remetente para realizar a busca de e-mails."
        
    gmail_logger.info(f"Executando buscar_emails: termo='{termo_busca}', qtd={quantidade}")
    mail, err = connect_imap()
    if err or not mail:
        return err

    try:
        mail.select("INBOX")
        # Busca por termo no assunto ou remetente
        query = f'(OR (SUBJECT "{termo_busca}") (FROM "{termo_busca}"))'
        status, data = mail.search(None, query)
        
        # Fallback para busca geral em texto se não encontrar
        if status != "OK" or not data or not data[0]:
            status, data = mail.search(None, f'(TEXT "{termo_busca}")')
            
        if status != "OK" or not data or not data[0]:
            mail.close()
            mail.logout()
            return f"Nenhum e-mail encontrado com o termo '{termo_busca}'."
            
        email_ids = data[0].split()
        selected_ids = email_ids[-quantidade:]
        selected_ids.reverse()
        
        resultados = []
        for msg_id in selected_ids:
            res, msg_data = mail.fetch(msg_id, "(RFC822)")
            if res != "OK" or not msg_data or not msg_data[0]:
                continue
                
            msg = email.message_from_bytes(msg_data[0][1])
            remetente = decode_mime_text(msg.get("From", "Desconhecido"))
            assunto = decode_mime_text(msg.get("Subject", "(Sem Assunto)"))
            data_envio = msg.get("Date", "")
            corpo = extract_plain_text(msg)
            previa = corpo[:300] + ("..." if len(corpo) > 300 else "") if corpo else "(Sem conteúdo de texto)"
            
            id_str = msg_id.decode("utf-8", errors="ignore")
            resultados.append(
                f"[ID: {id_str}]\n"
                f"Remetente: {remetente}\n"
                f"Assunto: {assunto}\n"
                f"Data: {data_envio}\n"
                f"Conteúdo: {previa}"
            )
            
        mail.close()
        mail.logout()
        return f"Encontrei {len(resultados)} e-mail(s) relacionados a '{termo_busca}':\n\n" + "\n\n---\n\n".join(resultados)
        
    except Exception as e:
        gmail_logger.error(f"Erro ao buscar e-mails: {e}")
        return f"Erro ao buscar e-mails no Gmail: {str(e)}"

@tool
def enviar_email(destinatario: str, assunto: str, mensagem: str) -> str:
    """
    Envia um novo e-mail para um destinatário através da conta configurada do Gmail.
    
    Args:
        destinatario: Endereço de e-mail do destinatário (ex: 'amigo@exemplo.com').
        assunto: Assunto / Título do e-mail.
        mensagem: Corpo do texto do e-mail a ser enviado.
    """
    user, _ = get_gmail_credentials()
    if not user:
        return "Credenciais do Gmail não configuradas no servidor."
        
    if not destinatario or "@" not in destinatario:
        return f"Endereço de e-mail destinatário inválido: '{destinatario}'."
        
    gmail_logger.info(f"Enviando e-mail para '{destinatario}' | Assunto: '{assunto}'")
    server, err = connect_smtp()
    if err or not server:
        return err

    try:
        msg = MIMEMultipart()
        msg["From"] = user
        msg["To"] = destinatario.strip()
        msg["Subject"] = assunto.strip()
        msg["Date"] = formatdate(localtime=True)
        
        msg.attach(MIMEText(mensagem.strip(), "plain", "utf-8"))
        
        server.send_message(msg)
        server.quit()
        
        gmail_logger.info(f"E-mail enviado com sucesso para {destinatario}!")
        return f"Sucesso: O e-mail com o assunto '{assunto}' foi enviado com sucesso para {destinatario}."
    except Exception as e:
        gmail_logger.error(f"Erro ao enviar e-mail: {e}")
        return f"Erro ao enviar e-mail: {str(e)}"

@tool
def responder_email(id_ou_assunto_email: str, resposta: str) -> str:
    """
    Responde a um e-mail existente na caixa de entrada do Gmail.
    Localiza o e-mail pelo ID numérico ou pelo assunto, obtém o remetente original e envia a resposta com 'Re: Assunto'.
    
    Args:
        id_ou_assunto_email: ID numérico do e-mail (ex: '124') ou palavra-chave do assunto original.
        resposta: Texto da mensagem de resposta a ser enviada.
    """
    user, _ = get_gmail_credentials()
    if not user:
        return "Credenciais do Gmail não configuradas no servidor."
        
    gmail_logger.info(f"Respondendo e-mail: ref='{id_ou_assunto_email}'")
    
    # 1. Localiza a mensagem original via IMAP
    mail, err = connect_imap()
    if err or not mail:
        return err
        
    target_msg = None
    try:
        mail.select("INBOX")
        target_id = None
        
        # Se for numérico (ID direto)
        clean_ref = id_ou_assunto_email.strip()
        if clean_ref.isdigit():
            target_id = clean_ref.encode("utf-8")
        else:
            # Busca por assunto
            status, data = mail.search(None, f'(SUBJECT "{clean_ref}")')
            if status == "OK" and data and data[0]:
                ids = data[0].split()
                target_id = ids[-1] # Mais recente com esse assunto
                
        if not target_id:
            mail.close()
            mail.logout()
            return f"Não foi possível encontrar o e-mail correspondente a '{id_ou_assunto_email}' para responder."
            
        res, msg_data = mail.fetch(target_id, "(RFC822)")
        if res == "OK" and msg_data and msg_data[0]:
            target_msg = email.message_from_bytes(msg_data[0][1])
            
        mail.close()
        mail.logout()
    except Exception as e:
        gmail_logger.error(f"Erro ao buscar e-mail original para resposta: {e}")
        return f"Erro ao localizar e-mail original: {str(e)}"
        
    if not target_msg:
        return f"Não foi possível ler o conteúdo do e-mail com identificador '{id_ou_assunto_email}'."

    # 2. Extrai destinatário e cabeçalhos para resposta
    reply_to = target_msg.get("Reply-To") or target_msg.get("From")
    _, dest_email = parseaddr(reply_to)
    if not dest_email:
        return f"Não foi possível identificar o endereço do remetente no e-mail: {reply_to}"
        
    original_subject = decode_mime_text(target_msg.get("Subject", ""))
    new_subject = original_subject if original_subject.lower().startswith("re:") else f"Re: {original_subject}"
    original_msg_id = target_msg.get("Message-ID", "")
    
    # 3. Envia a resposta via SMTP
    server, err_smtp = connect_smtp()
    if err_smtp or not server:
        return err_smtp

    try:
        msg = MIMEMultipart()
        msg["From"] = user
        msg["To"] = dest_email
        msg["Subject"] = new_subject
        msg["Date"] = formatdate(localtime=True)
        if original_msg_id:
            msg["In-Reply-To"] = original_msg_id
            msg["References"] = original_msg_id
            
        msg.attach(MIMEText(resposta.strip(), "plain", "utf-8"))
        
        server.send_message(msg)
        server.quit()
        
        gmail_logger.info(f"Resposta enviada com sucesso para {dest_email} (Assunto: {new_subject})")
        return f"Sucesso: Resposta enviada com sucesso para {dest_email} referente ao assunto '{new_subject}'."
    except Exception as e:
        gmail_logger.error(f"Erro ao enviar resposta de e-mail: {e}")
        return f"Erro ao enviar resposta de e-mail: {str(e)}"

def _move_ids_to_trash(mail: imaplib.IMAP4_SSL, ids: List[bytes]) -> int:
    """Move uma lista de IDs de e-mails para a Lixeira do Gmail e expunge da pasta atual."""
    if not ids:
        return 0
    
    id_set = b",".join(ids)
    trash_folders = ['"[Gmail]/Lixeira"', '"[Gmail]/Trash"', '"[Gmail]/Bin"', '"[Gmail]/Itens Excluídos"']
    moved = False
    
    for trash in trash_folders:
        try:
            res_copy, _ = mail.copy(id_set, trash)
            if res_copy == "OK":
                mail.store(id_set, "+FLAGS", "\\Deleted")
                moved = True
                break
        except Exception:
            continue
            
    if not moved:
        try:
            mail.store(id_set, "+FLAGS", "\\Deleted")
        except Exception:
            pass
        
    try:
        mail.expunge()
    except Exception:
        pass
        
    return len(ids)

@tool
def apagar_email(id_ou_assunto_email: str) -> str:
    """
    Move um e-mail específico ou todos os e-mails da Caixa de Entrada para a Lixeira do Gmail.
    
    Args:
        id_ou_assunto_email: ID numérico do e-mail (ex: '124'), palavra-chave do assunto ou remetente, ou 'todos' para limpar a caixa de entrada.
    """
    gmail_logger.info(f"Executando apagar_email: ref='{id_ou_assunto_email}'")
    mail, err = connect_imap()
    if err or not mail:
        return err

    try:
        mail.select("INBOX")
        clean_ref = (id_ou_assunto_email or "").strip()
        clean_lower = clean_ref.lower()
        
        # Caso o usuário tenha passado comandos como "todos", "all", "tudo", "todos os emails"
        if clean_lower in ["todos", "all", "tudo", "todos os emails", "todos os e-mails", "caixa de entrada", "inbox", "limpar"]:
            status, data = mail.search(None, "ALL")
            if status != "OK" or not data or not data[0]:
                try:
                    mail.close()
                    mail.logout()
                except Exception:
                    pass
                return "A sua caixa de entrada já está vazia. Não há e-mails para apagar."
            
            ids = data[0].split()
            count = _move_ids_to_trash(mail, ids)
            try:
                mail.close()
                mail.logout()
            except Exception:
                pass
            gmail_logger.info(f"Todos os {count} e-mails da caixa de entrada foram movidos para a lixeira.")
            return f"Sucesso: Todos os {count} e-mails da sua caixa de entrada foram movidos para a lixeira."

        target_ids = []
        assunto_info = clean_ref
        
        if clean_ref.isdigit():
            target_ids = [clean_ref.encode("utf-8")]
        else:
            # Tenta busca por Assunto
            status, data = mail.search(None, f'(SUBJECT "{clean_ref}")')
            if status == "OK" and data and data[0]:
                target_ids = data[0].split()
            else:
                # Tenta busca por Remetente (FROM)
                status, data = mail.search(None, f'(FROM "{clean_ref}")')
                if status == "OK" and data and data[0]:
                    target_ids = data[0].split()
                else:
                    # Tenta busca geral por TEXT
                    status, data = mail.search(None, f'(TEXT "{clean_ref}")')
                    if status == "OK" and data and data[0]:
                        target_ids = data[0].split()
                
        if not target_ids:
            try:
                mail.close()
                mail.logout()
            except Exception:
                pass
            return f"Não foi possível encontrar nenhum e-mail correspondente a '{id_ou_assunto_email}' para apagar."

        # Se for um único e-mail, obtém o assunto real para a resposta
        try:
            res, msg_data = mail.fetch(target_ids[-1], "(BODY.PEEK[HEADER.FIELDS (SUBJECT)])")
            if res == "OK" and msg_data and msg_data[0]:
                msg_hdr = email.message_from_bytes(msg_data[0][1])
                assunto_info = decode_mime_text(msg_hdr.get("Subject", clean_ref))
        except Exception:
            pass

        count = _move_ids_to_trash(mail, target_ids)
        try:
            mail.close()
            mail.logout()
        except Exception:
            pass
        
        if count == 1:
            gmail_logger.info(f"E-mail '{assunto_info}' movido para a lixeira.")
            return f"Sucesso: O e-mail com o assunto '{assunto_info}' foi movido para a lixeira com sucesso."
        else:
            gmail_logger.info(f"{count} e-mails correspondentes a '{clean_ref}' foram movidos para a lixeira.")
            return f"Sucesso: {count} e-mails correspondentes a '{clean_ref}' foram movidos para a lixeira com sucesso."
    except Exception as e:
        gmail_logger.error(f"Erro ao apagar e-mail: {e}")
        return f"Erro ao apagar e-mail no Gmail: {str(e)}"

@tool
def apagar_todos_emails(confirmacao: str = "sim") -> str:
    """
    Move TODOS os e-mails da Caixa de Entrada (INBOX) do Gmail para a Lixeira.
    Use sempre que o usuário pedir expressamente para apagar todos os e-mails, limpar toda a caixa de entrada ou excluir todas as mensagens.
    
    Args:
        confirmacao: Confirmação de exclusão ('sim' ou 'confirmado').
    """
    gmail_logger.info("Executando apagar_todos_emails")
    mail, err = connect_imap()
    if err or not mail:
        return err

    try:
        mail.select("INBOX")
        status, data = mail.search(None, "ALL")
        if status != "OK" or not data or not data[0]:
            try:
                mail.close()
                mail.logout()
            except Exception:
                pass
            return "A sua caixa de entrada já está vazia. Não há e-mails para apagar."

        ids = data[0].split()
        count = _move_ids_to_trash(mail, ids)
        try:
            mail.close()
            mail.logout()
        except Exception:
            pass
        
        gmail_logger.info(f"{count} e-mails foram movidos da Caixa de Entrada para a lixeira.")
        return f"Sucesso: Todos os {count} e-mails da sua caixa de entrada foram movidos para a lixeira com sucesso."
    except Exception as e:
        gmail_logger.error(f"Erro ao apagar todos os e-mails: {e}")
        return f"Erro ao apagar todos os e-mails no Gmail: {str(e)}"

import os
import sys
import io
import json
import asyncio
import threading
import base64
import edge_tts
from pathlib import Path
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, HTTPException, Depends, Header, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, EmailStr

# Adiciona caminhos para permitir executar tanto de dentro de api/ quanto da raiz do projeto
current_dir = Path(__file__).parent.resolve()
project_root = current_dir.parent.resolve()
for path in (str(current_dir), str(project_root)):
    if path not in sys.path:
        sys.path.insert(0, path)

try:
    from dotenv import load_dotenv
    load_dotenv(current_dir / ".env")
    load_dotenv(project_root / ".env")
except ImportError:
    pass

try:
    from api.agent import processar_comando_agente
    from api.auth import register_user, authenticate_user, create_access_token, decode_access_token, get_user_by_email
    from api.database import (
        get_user_profile, save_user_profile, get_chat_history, save_chat_message, clear_chat_history,
        db_create_task, db_get_tasks, db_complete_task, db_delete_task, db_get_tasks_count, db_get_contacts_count,
        db_create_note, db_get_notes, db_get_note_by_id_or_title, db_add_items_to_note, db_toggle_note_item, db_delete_note, db_get_notes_count,
        db_save_google_credentials, db_get_google_credentials,
        db_save_camera_config, db_get_camera_config,
        db_save_user_photo, db_get_user_photo, db_get_all_residents,
        db_save_telegram_config, db_get_telegram_config,
        db_save_ai_config, db_get_ai_config,
        db_create_automation, db_get_automations, db_get_automation_by_id,
        db_update_automation, db_delete_automation, db_toggle_automation,
        db_get_automations_count
    )
    from api.tools.vision_tools import capture_camera_frame, set_latest_browser_snapshot
    from api.telegram_bot import send_telegram_message, get_telegram_bot_info, telegram_manager
    from api.automation_engine import automation_engine, run_automation_now
    from api.logger import system_logger, auth_logger, vision_logger
except ImportError:
    from agent import processar_comando_agente
    from auth import register_user, authenticate_user, create_access_token, decode_access_token, get_user_by_email
    from database import (
        get_user_profile, save_user_profile, get_chat_history, save_chat_message, clear_chat_history,
        db_create_task, db_get_tasks, db_complete_task, db_delete_task, db_get_tasks_count, db_get_contacts_count,
        db_create_note, db_get_notes, db_get_note_by_id_or_title, db_add_items_to_note, db_toggle_note_item, db_delete_note, db_get_notes_count,
        db_save_google_credentials, db_get_google_credentials,
        db_save_camera_config, db_get_camera_config,
        db_save_user_photo, db_get_user_photo, db_get_all_residents,
        db_save_telegram_config, db_get_telegram_config,
        db_save_ai_config, db_get_ai_config,
        db_create_automation, db_get_automations, db_get_automation_by_id,
        db_update_automation, db_delete_automation, db_toggle_automation,
        db_get_automations_count
    )
    from tools.vision_tools import capture_camera_frame, set_latest_browser_snapshot
    from telegram_bot import send_telegram_message, get_telegram_bot_info, telegram_manager
    from automation_engine import automation_engine, run_automation_now
    from logger import system_logger, auth_logger, vision_logger

app = FastAPI(
    title="Smart Home AI Agent API",
    description="API com Autenticação JWT, SQLite, Perfil do Usuário, Memória Conversacional, Agente LangChain e Logs",
    version="2.4.0"
)

@app.on_event("startup")
def on_startup():
    system_logger.info("Servidor iniciando: sincronizando bots ativos do Telegram, automações e cache de TTS...")
    try:
        telegram_manager.restart_all_active_bots()
    except Exception as e:
        system_logger.error(f"Erro ao inicializar bots do Telegram no startup: {e}")
    try:
        automation_engine.start()
    except Exception as e_auto:
        system_logger.error(f"Erro ao inicializar AutomationEngine no startup: {e_auto}")
    try:
        prewarm_tts_cache_background()
    except Exception as e_tts:
        system_logger.error(f"Erro ao inicializar pré-aquecimento de TTS no startup: {e_tts}")

@app.on_event("shutdown")
def on_shutdown():
    system_logger.info("Servidor encerrando: finalizando motor de automações...")
    try:
        automation_engine.stop()
    except Exception as e:
        system_logger.error(f"Erro ao parar AutomationEngine: {e}")

# Habilitar CORS para permitir chamadas de qualquer frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================================================================
# SCHEMAS PYDANTIC
# =========================================================================

class RegisterRequest(BaseModel):
    name: str
    phone: Optional[str] = ""
    email: str
    password: str

class LoginRequest(BaseModel):
    email: str
    password: str

class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: Dict[str, Any]

class ProfileData(BaseModel):
    blood_type: Optional[str] = ""
    favorite_movies: Optional[str] = ""
    favorite_foods: Optional[str] = ""
    favorite_music: Optional[str] = ""
    favorite_places: Optional[str] = ""
    car_info: Optional[str] = ""
    allergies_health: Optional[str] = ""
    personal_notes: Optional[str] = ""
    photo_base64: Optional[str] = ""

class ChatRequest(BaseModel):
    message: str
    api_key: Optional[str] = None
    model: Optional[str] = "gemini-2.5-flash-lite"
    agent_name: Optional[str] = "Sexta-Feira"
    rooms: Optional[List[Dict[str, Any]]] = []
    rooms_state: Optional[Dict[str, bool]] = {}
    broker: Optional[str] = "test.mosquitto.org"
    port: Optional[int] = 1883
    user_email: Optional[str] = ""

class ChatResponse(BaseModel):
    reply: str
    actions: List[Dict[str, str]] = []

# =========================================================================
# DEPENDÊNCIA DE AUTENTICAÇÃO JWT
# =========================================================================

def get_current_user_token(authorization: Optional[str] = Header(None)):
    """Valida o cabeçalho Authorization: Bearer <token>."""
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token JWT ausente. Faça login para acessar este recurso."
        )
    
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Formato de token inválido. Use 'Bearer <token>'."
        )
        
    token = parts[1]
    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token JWT expirado ou inválido."
        )
    return payload

# =========================================================================
# ROTAS DE AUTENTICAÇÃO (SQLite + JWT)
# =========================================================================

@app.post("/api/auth/register", response_model=AuthResponse)
def register_endpoint(request: RegisterRequest):
    try:
        user = register_user(
            name=request.name,
            phone=request.phone or "",
            email=request.email,
            password=request.password
        )
        token = create_access_token({"sub": user["email"], "id": user["id"], "name": user["name"]})
        return AuthResponse(
            access_token=token,
            user={"id": user["id"], "name": user["name"], "phone": user["phone"], "email": user["email"]}
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        auth_logger.error(f"Erro inesperado no cadastro: {e}")
        raise HTTPException(status_code=500, detail="Erro interno ao realizar cadastro.")

@app.post("/api/auth/login", response_model=AuthResponse)
def login_endpoint(request: LoginRequest):
    user = authenticate_user(request.email, request.password)
    if not user:
        raise HTTPException(status_code=401, detail="E-mail ou senha incorretos.")
        
    token = create_access_token({"sub": user["email"], "id": user["id"], "name": user["name"]})
    return AuthResponse(
        access_token=token,
        user=user
    )

@app.get("/api/auth/me")
def me_endpoint(token_payload: dict = Depends(get_current_user_token)):
    user = get_user_by_email(token_payload.get("sub", ""))
    if not user:
        raise HTTPException(status_code=404, detail="Usuário não encontrado.")
    return {
        "id": user["id"],
        "name": user["name"],
        "phone": user.get("phone", ""),
        "email": user["email"]
    }

# =========================================================================
# ROTAS DO PERFIL DO USUÁRIO (SQLite)
# =========================================================================

class UserPhotoUploadRequest(BaseModel):
    photo_base64: str

@app.get("/api/profile")
def get_profile_endpoint(token_payload: dict = Depends(get_current_user_token)):
    user_email = token_payload.get("sub", "")
    profile = get_user_profile(user_email)
    return profile

@app.post("/api/profile")
def save_profile_endpoint(data: ProfileData, token_payload: dict = Depends(get_current_user_token)):
    user_email = token_payload.get("sub", "")
    saved_profile = save_user_profile(user_email, data.model_dump())
    return {"message": "Perfil atualizado com sucesso!", "profile": saved_profile}

@app.get("/api/user/photo")
def get_user_photo_endpoint(token_payload: dict = Depends(get_current_user_token)):
    """Retorna a foto de perfil/referência facial do usuário logado."""
    user_email = token_payload.get("sub", "")
    photo = db_get_user_photo(user_email)
    return {
        "user_email": user_email,
        "has_photo": bool(photo and len(photo) > 50),
        "photo_base64": photo
    }

@app.post("/api/user/photo")
def save_user_photo_endpoint(
    req: UserPhotoUploadRequest,
    token_payload: dict = Depends(get_current_user_token)
):
    """Salva e otimiza a foto de referência facial do usuário para reconhecimento pela IA."""
    user_email = token_payload.get("sub", "")
    raw_b64 = req.photo_base64.strip()
    if not raw_b64:
        raise HTTPException(status_code=400, detail="Imagem não fornecida.")
        
    try:
        b64_content = raw_b64
        if "base64," in raw_b64:
            b64_content = raw_b64.split("base64,", 1)[1]
            
        img_bytes = base64.b64decode(b64_content)
        from PIL import Image
        img = Image.open(io.BytesIO(img_bytes))
        img = img.convert("RGB")
        img.thumbnail((400, 400), Image.Resampling.LANCZOS)
        
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85, optimize=True)
        optimized_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        final_photo = f"data:image/jpeg;base64,{optimized_b64}"
        
        db_save_user_photo(user_email, final_photo)
        system_logger.info(f"Foto de perfil/reconhecimento facial salva para {user_email} ({len(buf.getvalue())} bytes)")
        return {
            "status": "success",
            "message": "Foto de perfil e referência facial salva com sucesso!",
            "has_photo": True,
            "photo_base64": final_photo
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erro ao processar imagem: {e}")

@app.delete("/api/user/photo")
def delete_user_photo_endpoint(token_payload: dict = Depends(get_current_user_token)):
    """Remove a foto de perfil/referência facial do usuário."""
    user_email = token_payload.get("sub", "")
    db_save_user_photo(user_email, "")
    return {
        "status": "success",
        "message": "Foto de perfil removida com sucesso.",
        "has_photo": False
    }

@app.get("/api/residents")
def get_residents_endpoint(token_payload: dict = Depends(get_current_user_token)):
    """Retorna a lista de todos os moradores cadastrados no sistema."""
    residents = db_get_all_residents()
    return {
        "total": len(residents),
        "residents": [
            {
                "user_id": r["user_id"],
                "name": r["name"],
                "email": r["email"],
                "has_photo": r["has_photo"],
                "personal_notes": r["personal_notes"]
            }
            for r in residents
        ]
    }

# =========================================================================
# ROTAS DE HISTÓRICO / MEMÓRIA DE CHAT
# =========================================================================

@app.get("/api/chat/history")
def get_chat_history_endpoint(limit: int = 5, token_payload: dict = Depends(get_current_user_token)):
    user_email = token_payload.get("sub", "")
    history = get_chat_history(user_email, limit=limit)
    return {"user_email": user_email, "count": len(history), "history": history}

@app.delete("/api/chat/history")
def clear_chat_history_endpoint(token_payload: dict = Depends(get_current_user_token)):
    user_email = token_payload.get("sub", "")
    success = clear_chat_history(user_email)
    return {"message": "Histórico de mensagens limpo com sucesso.", "success": success}

# =========================================================================
# ROTA DO AGENTE INTELIGENTE (COM MEMÓRIA CONVERSACIONAL)
# =========================================================================

@app.post("/api/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest, token_payload: dict = Depends(get_current_user_token)):
    user_email = token_payload.get("sub") or request.user_email or ""
    system_logger.info(f"Requisição /api/chat recebida do usuário: {user_email}")
    
    # Carrega preferências e chave de API do banco de dados do usuário (com fallback para requisição/env)
    ai_cfg = db_get_ai_config(user_email) if user_email else {}
    api_key = (request.api_key or ai_cfg.get("api_key") or os.getenv("GEMINI_API_KEY") or os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        system_logger.warning("Tentativa de chamada sem Chave de API configurada.")
        raise HTTPException(
            status_code=400,
            detail="Chave de API não fornecida. Configure sua chave no painel de configurações."
        )
        
    model_name = (request.model or ai_cfg.get("ai_model") or os.getenv("DEFAULT_MODEL", "gemini-2.5-flash-lite")).strip()
    user_profile = get_user_profile(user_email) if user_email else {}
    chat_history = get_chat_history(user_email, limit=5) if user_email else []

    try:
        resultado = processar_comando_agente(
            pergunta=request.message,
            api_key=api_key,
            modelo=model_name,
            agent_name=request.agent_name or "Sexta-Feira",
            rooms=request.rooms,
            rooms_state=request.rooms_state,
            broker_config={"broker": request.broker, "port": request.port},
            user_email=user_email,
            user_profile=user_profile,
            chat_history=chat_history
        )
        
        reply_text = resultado.get("reply", "Comando processado.")
        
        # Salva a interação (pergunta + resposta) na tabela de histórico SQLite do usuário
        if user_email and reply_text:
            try:
                save_chat_message(
                    user_email=user_email,
                    user_message=request.message,
                    agent_response=reply_text
                )
            except Exception as err_hist:
                system_logger.warning(f"Falha ao persistir interação no histórico: {err_hist}")

        return ChatResponse(
            reply=reply_text,
            actions=resultado.get("actions", [])
        )
    except Exception as e:
        system_logger.error(f"Erro no processamento do agente: {e}")
        raise HTTPException(status_code=500, detail=f"Erro no processamento do agente: {str(e)}")

@app.post("/api/chat/stream")
async def chat_stream_endpoint(request: ChatRequest, token_payload: dict = Depends(get_current_user_token)):
    """
    Endpoint SSE (Server-Sent Events) que transmite o progresso e raciocínio do agente em tempo real:
    - data: {"type": "status", "message": "Consultando seus compromissos no Google Agenda...", "extra": {...}}
    - data: {"type": "final", "reply": "...", "actions": [...]}
    - data: {"type": "error", "message": "..."}
    """
    user_email = token_payload.get("sub") or request.user_email or ""
    system_logger.info(f"Requisição /api/chat/stream recebida do usuário: {user_email}")

    ai_cfg = db_get_ai_config(user_email) if user_email else {}
    api_key = (request.api_key or ai_cfg.get("api_key") or os.getenv("GEMINI_API_KEY") or os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        raise HTTPException(
            status_code=400,
            detail="Chave de API não fornecida. Configure sua chave no painel de configurações."
        )

    model_name = (request.model or ai_cfg.get("ai_model") or os.getenv("DEFAULT_MODEL", "gemini-2.5-flash-lite")).strip()
    user_profile = get_user_profile(user_email) if user_email else {}
    chat_history = get_chat_history(user_email, limit=5) if user_email else []

    async def event_generator():
        queue: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def status_callback(event_type: str, message: str, extra: Optional[Dict[str, Any]] = None):
            loop.call_soon_threadsafe(
                queue.put_nowait,
                {"type": event_type, "message": message, "extra": extra or {}}
            )

        def worker():
            try:
                status_callback("status", "Analisando sua solicitação...")
                res = processar_comando_agente(
                    pergunta=request.message,
                    api_key=api_key,
                    modelo=model_name,
                    agent_name=request.agent_name or "Sexta-Feira",
                    rooms=request.rooms,
                    rooms_state=request.rooms_state,
                    broker_config={"broker": request.broker, "port": request.port},
                    user_email=user_email,
                    user_profile=user_profile,
                    chat_history=chat_history,
                    status_callback=status_callback
                )

                reply_text = res.get("reply", "Comando processado com sucesso.")
                actions = res.get("actions", [])

                if user_email and reply_text:
                    try:
                        save_chat_message(
                            user_email=user_email,
                            user_message=request.message,
                            agent_response=reply_text
                        )
                    except Exception as err_hist:
                        system_logger.warning(f"Falha ao persistir interação no histórico: {err_hist}")

                loop.call_soon_threadsafe(
                    queue.put_nowait,
                    {"type": "final", "reply": reply_text, "actions": actions}
                )
            except Exception as e:
                system_logger.error(f"Erro no processamento do agente stream: {e}")
                loop.call_soon_threadsafe(
                    queue.put_nowait,
                    {"type": "error", "message": str(e)}
                )
            finally:
                loop.call_soon_threadsafe(queue.put_nowait, None)

        threading.Thread(target=worker, daemon=True).start()

        while True:
            item = await queue.get()
            if item is None:
                break
            yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

@app.get("/health")
def health_check():
    return {"status": "ok", "service": "Smart Home AI Agent API", "db": "SQLite"}

# =========================================================================
# STATUS E INTEGRAÇÕES DO AGENTE
# =========================================================================

@app.get("/api/agent/status")
def agent_status_endpoint(token_payload: dict = Depends(get_current_user_token)):
    user_email = token_payload.get("sub", "")
    
    gmail_user, gmail_pwd = db_get_google_credentials(user_email)
    gmail_ok = bool(gmail_user and gmail_pwd)
    
    # Contagem de mensagens no SQLite e configurações
    history = get_chat_history(user_email, limit=50)
    profile = get_user_profile(user_email)
    cam_cfg = db_get_camera_config(user_email)
    tg_cfg = db_get_telegram_config(user_email)
    
    return {
        "status": "online",
        "user_email": user_email,
        "agent_name": "Sexta-Feira",
        "default_model": "gemini-2.5-flash-lite",
        "integrations": {
            "gmail": {
                "name": "Gmail",
                "connected": gmail_ok,
                "account": gmail_user if gmail_ok else None,
                "protocol": "IMAP / SMTP (SSL/TLS)"
            },
            "calendar": {
                "name": "Google Calendar",
                "connected": gmail_ok,
                "account": gmail_user if gmail_ok else None,
                "protocol": "Google CalDAV"
            },
            "contacts": {
                "name": "Google Contacts",
                "connected": gmail_ok,
                "account": gmail_user if gmail_ok else None,
                "protocol": "Google CardDAV",
                "contacts_count": db_get_contacts_count(user_email)
            },
            "tasks": {
                "name": "Google Tasks & Lembretes",
                "connected": True,
                "pending_count": db_get_tasks_count(user_email, "pendente"),
                "total_count": db_get_tasks_count(user_email, "todas"),
                "protocol": "SQLite + Google Calendar Sync"
            },
            "notes": {
                "name": "Google Keep & Listas de Compras",
                "connected": True,
                "notes_count": db_get_notes_count(user_email, "todas"),
                "shopping_lists_count": db_get_notes_count(user_email, "lista"),
                "protocol": "SQLite + Checklists"
            },
            "camera": {
                "name": "Visão & Câmera (Local / IP)",
                "connected": True,
                "type": cam_cfg.get("camera_type", "device"),
                "ip_url": cam_cfg.get("camera_ip_url", "") if cam_cfg.get("camera_type") == "ip" else None,
                "auto_greeting": cam_cfg.get("camera_auto_greeting", True),
                "protocol": "OpenCV / RTSP / Multimodal LLM Vision"
            },
            "telegram": {
                "name": "Telegram Bot & Controle Remoto",
                "connected": bool(tg_cfg.get("configured")),
                "enabled": bool(tg_cfg.get("enabled")),
                "chat_id": tg_cfg.get("chat_id") if tg_cfg.get("chat_id") else None,
                "protocol": "Telegram Bot API (Long-Polling)"
            },
            "mqtt": {
                "name": "Automação Residencial MQTT",
                "connected": True,
                "broker": "test.mosquitto.org:1883"
            },
            "search": {
                "name": "Pesquisa na Web",
                "connected": True,
                "engine": "DuckDuckGo Realtime"
            },
            "memory": {
                "name": "Memória Conversacional & Perfil",
                "connected": True,
                "db": "SQLite (smarthome.db)",
                "history_count": len(history),
                "has_profile": bool(profile.get("blood_type") or profile.get("favorite_foods"))
            },
            "automations": {
                "name": "Automações & 2º Plano",
                "connected": automation_engine.is_running(),
                "active_count": db_get_automations_count(user_email)["active"],
                "total_count": db_get_automations_count(user_email)["total"],
                "protocol": "Background Engine (Cron / CalDAV / MQTT / Telegram)"
            }
        }
    }

# =========================================================================
# ENDPOINTS REST DE TAREFAS E LEMBRETES (TASKS)
# =========================================================================

class TaskCreateRequest(BaseModel):
    title: str
    description: Optional[str] = ""
    due_date: Optional[str] = ""
    due_time: Optional[str] = ""
    priority: Optional[str] = "media"

@app.get("/api/tasks")
def get_tasks_endpoint(
    status: str = "pendente",
    filter_date: str = "todas",
    limit: int = 50,
    token_payload: dict = Depends(get_current_user_token)
):
    user_email = token_payload.get("sub", "")
    tasks = db_get_tasks(user_email, status=status, filter_date=filter_date, limit=limit)
    return {"tasks": tasks, "total": len(tasks), "pending_count": db_get_tasks_count(user_email, "pendente")}

@app.post("/api/tasks")
def create_task_endpoint(
    req: TaskCreateRequest,
    token_payload: dict = Depends(get_current_user_token)
):
    user_email = token_payload.get("sub", "")
    task = db_create_task(
        user_email=user_email,
        title=req.title,
        description=req.description or "",
        due_date=req.due_date or "",
        due_time=req.due_time or "",
        priority=req.priority or "media"
    )
    return {"status": "success", "task": task}

@app.patch("/api/tasks/{task_id}/complete")
def complete_task_endpoint(
    task_id: int,
    token_payload: dict = Depends(get_current_user_token)
):
    user_email = token_payload.get("sub", "")
    task = db_complete_task(user_email, str(task_id))
    if not task:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada ou já concluída.")
    return {"status": "success", "task": task}

@app.delete("/api/tasks/{task_id}")
def delete_task_endpoint(
    task_id: int,
    token_payload: dict = Depends(get_current_user_token)
):
    user_email = token_payload.get("sub", "")
    deleted = db_delete_task(user_email, str(task_id))
    if not deleted:
        raise HTTPException(status_code=404, detail="Tarefa não encontrada.")
    return {"status": "success", "task": deleted}

# =========================================================================
# ENDPOINTS REST DE NOTAS E LISTAS DE COMPRAS (GOOGLE KEEP / NOTES)
# =========================================================================

class NoteCreateRequest(BaseModel):
    title: str
    content: Optional[str] = ""
    note_type: Optional[str] = "texto"
    color: Optional[str] = "padrao"
    is_pinned: Optional[bool] = False
    items: Optional[List[str]] = []

class NoteAddItemRequest(BaseModel):
    items: List[str]

class NoteToggleItemRequest(BaseModel):
    item_text: str
    is_completed: Optional[bool] = True

@app.get("/api/notes")
def get_notes_endpoint(
    note_type: str = "todas",
    limit: int = 50,
    token_payload: dict = Depends(get_current_user_token)
):
    user_email = token_payload.get("sub", "")
    notes = db_get_notes(user_email, note_type=note_type, limit=limit)
    return {"notes": notes, "total": len(notes)}

@app.get("/api/notes/{note_id}")
def get_note_detail_endpoint(
    note_id: str,
    token_payload: dict = Depends(get_current_user_token)
):
    user_email = token_payload.get("sub", "")
    note = db_get_note_by_id_or_title(user_email, note_id)
    if not note:
        raise HTTPException(status_code=404, detail="Nota não encontrada.")
    return {"note": note}

@app.post("/api/notes")
def create_note_endpoint(
    req: NoteCreateRequest,
    token_payload: dict = Depends(get_current_user_token)
):
    user_email = token_payload.get("sub", "")
    note = db_create_note(
        user_email=user_email,
        title=req.title,
        content=req.content or "",
        note_type=req.note_type or "texto",
        color=req.color or "padrao",
        is_pinned=req.is_pinned or False,
        items=req.items or []
    )
    return {"status": "success", "note": note}

@app.post("/api/notes/{note_id}/items")
def add_note_items_endpoint(
    note_id: str,
    req: NoteAddItemRequest,
    token_payload: dict = Depends(get_current_user_token)
):
    user_email = token_payload.get("sub", "")
    note = db_add_items_to_note(user_email, note_id, req.items)
    if not note:
        raise HTTPException(status_code=404, detail="Nota não encontrada.")
    return {"status": "success", "note": note}

@app.patch("/api/notes/{note_id}/items")
def toggle_note_item_endpoint(
    note_id: str,
    req: NoteToggleItemRequest,
    token_payload: dict = Depends(get_current_user_token)
):
    user_email = token_payload.get("sub", "")
    note = db_toggle_note_item(user_email, note_id, req.item_text, is_completed=req.is_completed)
    if not note:
        raise HTTPException(status_code=404, detail="Item ou nota não encontrados.")
    return {"status": "success", "note": note}

@app.delete("/api/notes/{note_id}")
def delete_note_endpoint(
    note_id: str,
    token_payload: dict = Depends(get_current_user_token)
):
    user_email = token_payload.get("sub", "")
    deleted = db_delete_note(user_email, note_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Nota não encontrada.")
    return {"status": "success", "note": deleted}

# =========================================================================
# ENDPOINTS DE CONFIGURAÇÃO DE CREDENCIAIS GOOGLE DO USUÁRIO
# =========================================================================

class GoogleCredentialsRequest(BaseModel):
    gmail_email: str
    gmail_app_password: str

@app.get("/api/user/google-credentials")
def get_user_google_credentials_endpoint(token_payload: dict = Depends(get_current_user_token)):
    """Retorna o status das credenciais Google do usuário logado (com senha mascarada)."""
    user_email = token_payload.get("sub", "")
    gmail_user, gmail_pwd = db_get_google_credentials(user_email)
    
    masked_pwd = ""
    if gmail_pwd:
        if len(gmail_pwd) >= 8:
            masked_pwd = gmail_pwd[:2] + ("*" * (len(gmail_pwd) - 4)) + gmail_pwd[-2:]
        else:
            masked_pwd = "********"
            
    return {
        "configured": bool(gmail_user and gmail_pwd),
        "gmail_email": gmail_user,
        "masked_password": masked_pwd
    }

@app.post("/api/user/google-credentials")
def save_user_google_credentials_endpoint(
    req: GoogleCredentialsRequest,
    token_payload: dict = Depends(get_current_user_token)
):
    """Salva o e-mail e a senha de aplicativo Google do usuário logado no banco de dados."""
    user_email = token_payload.get("sub", "")
    res = db_save_google_credentials(user_email, req.gmail_email, req.gmail_app_password)
    return {
        "status": "success",
        "message": "Credenciais da Conta Google salvas com sucesso!",
        "configured": res["configured"],
        "gmail_email": res["gmail_email"]
    }

@app.post("/api/user/google-credentials/test")
def test_user_google_credentials_endpoint(
    req: Optional[GoogleCredentialsRequest] = None,
    token_payload: dict = Depends(get_current_user_token)
):
    """Testa a conectividade ao vivo com o Gmail (IMAP), Google Calendar (CalDAV) e Google Contacts (CardDAV)."""
    user_email = token_payload.get("sub", "")
    req_email = (req.gmail_email or "").strip() if req else ""
    req_pwd = (req.gmail_app_password or "").replace(" ", "").strip() if req else ""
    is_masked = bool("*" in req_pwd or "•" in req_pwd)

    if req_email and req_pwd and not is_masked:
        gmail_user = req_email
        gmail_pwd = req_pwd
    else:
        db_user, db_pwd = db_get_google_credentials(user_email)
        gmail_user = req_email if req_email else db_user
        gmail_pwd = db_pwd
        
    if not gmail_user or not gmail_pwd:
        return {
            "success": False,
            "imap": False,
            "caldav": False,
            "carddav": False,
            "message": "E-mail ou senha de aplicativo do Google não configurados."
        }
        
    results = {"imap": False, "caldav": False, "carddav": False, "errors": []}
    
    # 1. Teste IMAP (Gmail)
    try:
        import imaplib
        imap_client = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        imap_client.login(gmail_user, gmail_pwd)
        imap_client.logout()
        results["imap"] = True
    except Exception as e_imap:
        results["errors"].append(f"Gmail IMAP: {e_imap}")
        
    # 2. Teste CalDAV (Google Calendar)
    try:
        import caldav
        cal_client = caldav.DAVClient(
            url=f"https://calendar.google.com/calendar/dav/{gmail_user}/user",
            username=gmail_user,
            password=gmail_pwd
        )
        principal = cal_client.principal()
        calendars = principal.calendars()
        results["caldav"] = len(calendars) > 0
    except Exception as e_cal:
        results["errors"].append(f"Google Calendar: {e_cal}")
        
    # 3. Teste CardDAV (Google Contacts)
    try:
        import requests
        card_url = f"https://www.googleapis.com/carddav/v1/principals/{gmail_user}/lists/default/"
        xml_body = """<d:propfind xmlns:d="DAV:"><d:prop><d:displayname /></d:prop></d:propfind>"""
        resp = requests.request(
            "PROPFIND",
            card_url,
            data=xml_body,
            auth=(gmail_user, gmail_pwd),
            headers={"Depth": "1", "Content-Type": "application/xml; charset=utf-8"},
            timeout=10
        )
        results["carddav"] = resp.status_code in (200, 207, 429)
    except Exception as e_card:
        results["errors"].append(f"Google Contacts: {e_card}")
        
    overall_success = results["imap"] or results["caldav"] or results["carddav"]
    msg = "Conexão com os serviços Google validada com sucesso!" if (results["imap"] and results["caldav"]) else "Conexão parcial com o Google."
    if not overall_success:
        msg = f"Falha na autenticação: {'; '.join(results['errors']) if results['errors'] else 'Credenciais inválidas'}"
        
    return {
        "success": overall_success,
        "imap": results["imap"],
        "caldav": results["caldav"],
        "carddav": results["carddav"],
        "message": msg,
        "errors": results["errors"]
    }

# =========================================================================
# ENDPOINTS DE CONFIGURAÇÃO E TESTE DE CÂMERA & VISÃO
# =========================================================================

class CameraConfigRequest(BaseModel):
    camera_type: Optional[str] = "device"
    camera_ip_url: Optional[str] = ""
    camera_username: Optional[str] = ""
    camera_password: Optional[str] = ""
    camera_auto_greeting: Optional[bool] = True
    camera_device_index: Optional[int] = 0

class CameraSnapshotUploadRequest(BaseModel):
    image_base64: str

@app.get("/api/user/camera-config")
def get_user_camera_config_endpoint(token_payload: dict = Depends(get_current_user_token)):
    """Retorna as configurações de câmera do usuário logado (com senha mascarada)."""
    user_email = token_payload.get("sub", "")
    cfg = db_get_camera_config(user_email)
    pwd = cfg.get("camera_password", "")
    masked_pwd = ("*" * len(pwd)) if pwd else ""
    return {
        "camera_type": cfg.get("camera_type", "device"),
        "camera_ip_url": cfg.get("camera_ip_url", ""),
        "camera_username": cfg.get("camera_username", ""),
        "masked_password": masked_pwd,
        "camera_auto_greeting": cfg.get("camera_auto_greeting", True),
        "camera_device_index": cfg.get("camera_device_index", 0)
    }

@app.post("/api/user/camera-config")
def save_user_camera_config_endpoint(
    req: CameraConfigRequest,
    token_payload: dict = Depends(get_current_user_token)
):
    """Salva as configurações de câmera (dispositivo local ou IP) do usuário."""
    user_email = token_payload.get("sub", "")
    current = db_get_camera_config(user_email)
    pwd = req.camera_password if req.camera_password is not None and req.camera_password != "" else current.get("camera_password", "")
    
    res = db_save_camera_config(
        user_email=user_email,
        camera_type=req.camera_type or "device",
        camera_ip_url=req.camera_ip_url or "",
        camera_username=req.camera_username or "",
        camera_password=pwd or "",
        camera_auto_greeting=bool(req.camera_auto_greeting),
        camera_device_index=int(req.camera_device_index or 0)
    )
    return {
        "status": "success",
        "message": "Configurações de câmera salvas com sucesso!",
        "config": res
    }

@app.post("/api/user/camera-config/test")
def test_user_camera_config_endpoint(
    req: Optional[CameraConfigRequest] = None,
    token_payload: dict = Depends(get_current_user_token)
):
    """Testa a captura de um quadro da câmera (Dispositivo ou IP) e retorna snapshot em base64."""
    user_email = token_payload.get("sub", "")
    cfg = db_get_camera_config(user_email)
    if req:
        if req.camera_type:
            cfg["camera_type"] = req.camera_type
        if req.camera_ip_url is not None:
            cfg["camera_ip_url"] = req.camera_ip_url
        if req.camera_username is not None:
            cfg["camera_username"] = req.camera_username
        if req.camera_password:
            cfg["camera_password"] = req.camera_password
        if req.camera_device_index is not None:
            cfg["camera_device_index"] = req.camera_device_index
            
    frame_bytes, err = capture_camera_frame(cfg)
    if frame_bytes:
        b64 = base64.b64encode(frame_bytes).decode("utf-8")
        return {
            "success": True,
            "message": "Quadro da câmera capturado com sucesso!",
            "snapshot_base64": f"data:image/jpeg;base64,{b64}"
        }
    else:
        return {
            "success": False,
            "message": err or "Não foi possível capturar imagem da câmera.",
            "snapshot_base64": None
        }

@app.post("/api/camera/snapshot")
def upload_browser_camera_snapshot_endpoint(
    req: CameraSnapshotUploadRequest,
    token_payload: dict = Depends(get_current_user_token)
):
    """Recebe um snapshot da webcam do navegador para uso pelo agente em visão computacional."""
    user_email = token_payload.get("sub", "")
    try:
        raw_b64 = req.image_base64
        if "base64," in raw_b64:
            raw_b64 = raw_b64.split("base64,", 1)[1]
        img_bytes = base64.b64decode(raw_b64)
        set_latest_browser_snapshot(user_email, img_bytes)
        return {"status": "success", "bytes_received": len(img_bytes)}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erro ao processar imagem base64: {e}")

# =========================================================================
# ENDPOINTS DE CONFIGURAÇÃO E TESTE DO TELEGRAM BOT
# =========================================================================

class TelegramConfigRequest(BaseModel):
    bot_token: str
    chat_id: Optional[str] = ""
    enabled: Optional[bool] = True
    notify_camera: Optional[bool] = True
    notify_tasks: Optional[bool] = True

class TelegramTestRequest(BaseModel):
    bot_token: Optional[str] = ""
    chat_id: Optional[str] = ""

@app.get("/api/user/telegram-config")
def get_user_telegram_config_endpoint(token_payload: dict = Depends(get_current_user_token)):
    """Retorna a configuração do Telegram do usuário logado (com token mascarado)."""
    user_email = token_payload.get("sub", "")
    cfg = db_get_telegram_config(user_email)
    token = cfg.get("bot_token", "")
    masked_token = ""
    if token:
        if len(token) > 10:
            masked_token = token[:4] + ("*" * (len(token) - 8)) + token[-4:]
        else:
            masked_token = "********"
            
    return {
        "configured": cfg.get("configured", False),
        "bot_token": token,
        "masked_token": masked_token,
        "chat_id": cfg.get("chat_id", ""),
        "enabled": cfg.get("enabled", False),
        "notify_camera": cfg.get("notify_camera", True),
        "notify_tasks": cfg.get("notify_tasks", True)
    }

@app.post("/api/user/telegram-config")
def save_user_telegram_config_endpoint(
    req: TelegramConfigRequest,
    token_payload: dict = Depends(get_current_user_token)
):
    """Salva o token, Chat ID e preferências do Telegram e inicia/reinicia o bot em background."""
    user_email = token_payload.get("sub", "")
    current = db_get_telegram_config(user_email)
    
    clean_token = req.bot_token.strip() if req.bot_token is not None and req.bot_token != "" else current.get("bot_token", "")
    clean_chat_id = req.chat_id.strip() if req.chat_id is not None else current.get("chat_id", "")
    
    res = db_save_telegram_config(
        user_email=user_email,
        bot_token=clean_token,
        chat_id=clean_chat_id,
        enabled=bool(req.enabled),
        notify_camera=bool(req.notify_camera),
        notify_tasks=bool(req.notify_tasks)
    )
    
    # Atualiza o gerenciador de polling do bot
    if req.enabled and clean_token:
        telegram_manager.start_bot_for_user(user_email, clean_token, clean_chat_id)
    else:
        telegram_manager.stop_bot_for_user(user_email)
        
    return {
        "status": "success",
        "message": "Configurações do Telegram salvas com sucesso!",
        "config": res
    }

@app.post("/api/user/telegram-config/test")
def test_user_telegram_config_endpoint(
    req: Optional[TelegramTestRequest] = None,
    token_payload: dict = Depends(get_current_user_token)
):
    """Testa o token do Bot do Telegram e envia uma mensagem de teste se o chat_id estiver preenchido."""
    user_email = token_payload.get("sub", "")
    cfg = db_get_telegram_config(user_email)
    
    token = (req.bot_token if req and req.bot_token else cfg.get("bot_token", "")).strip()
    chat_id = (req.chat_id if req and req.chat_id is not None else cfg.get("chat_id", "")).strip()
    
    if not token:
        raise HTTPException(status_code=400, detail="Token do bot do Telegram não informado.")
        
    # Valida token com getMe
    bot_info, err = get_telegram_bot_info(token)
    if not bot_info:
        raise HTTPException(status_code=400, detail=f"Token inválido: {err or 'Falha ao conectar na API do Telegram'}")
        
    bot_name = bot_info.get("first_name", "Bot")
    bot_username = bot_info.get("username", "")
    
    msg_status = "Token válido!"
    sent_ok = False
    if chat_id:
        test_text = (
            f"🤖 Olá! Mensagem de teste da assistente residencial **Sexta-Feira**.\n\n"
            f"✅ A integração com seu Telegram e a Smart Home ({user_email}) está conectada e operacional!"
        )
        sent_ok, msg_err = send_telegram_message(token, chat_id, test_text, parse_mode="Markdown")
        if sent_ok:
            msg_status = f"Token válido (@{bot_username}) e mensagem de teste enviada com sucesso para o Chat ID {chat_id}!"
        else:
            msg_status = f"Token válido (@{bot_username}), mas falha ao enviar mensagem para o Chat ID {chat_id}: {msg_err}"
    else:
        msg_status = f"Token válido (@{bot_username})! Para receber mensagens, inicie uma conversa com @{bot_username} e envie /start no Telegram."
        
    return {
        "status": "success",
        "valid_token": True,
        "bot_name": bot_name,
        "bot_username": bot_username,
        "message_sent": sent_ok,
        "details": msg_status
    }

# =========================================================================
# CONFIGURAÇÃO DE IA, MODELO E VOZ DO USUÁRIO (SQLite)
# =========================================================================

class UserAiConfigRequest(BaseModel):
    api_key: Optional[str] = None
    ai_model: Optional[str] = None
    voice: Optional[str] = None

@app.get("/api/user/ai-config")
def get_user_ai_config_endpoint(token_payload: dict = Depends(get_current_user_token)):
    """Retorna as preferências de IA, modelo e voz salvas para o usuário logado."""
    user_email = token_payload.get("sub", "")
    if not user_email:
        raise HTTPException(status_code=401, detail="Usuário não autenticado.")
    return db_get_ai_config(user_email)

@app.post("/api/user/ai-config")
def save_user_ai_config_endpoint(
    req: UserAiConfigRequest,
    token_payload: dict = Depends(get_current_user_token)
):
    """Salva a chave de API, modelo e voz selecionados diretamente no perfil SQLite do usuário."""
    user_email = token_payload.get("sub", "")
    if not user_email:
        raise HTTPException(status_code=401, detail="Usuário não autenticado.")
        
    saved = db_save_ai_config(
        user_email=user_email,
        api_key=req.api_key if req.api_key is not None else "",
        ai_model=req.ai_model if req.ai_model is not None else "",
        voice=req.voice if req.voice is not None else ""
    )
    return {"status": "success", "config": saved}

# =========================================================================
# ENDPOINTS REST DE MOTOR DE AUTOMAÇÕES E AGENDAMENTOS EM SEGUNDO PLANO
# =========================================================================

class AutomationCreateRequest(BaseModel):
    name: str
    automation_type: str  # calendar_reminder, daily_summary, mqtt_schedule, custom_prompt, telegram_alert
    trigger_type: str     # event_relative_minutes, daily_time, interval_minutes
    trigger_value: str    # "15", "08:00", "30"
    action_type: str      # telegram_alert, mqtt_command, agent_prompt
    action_payload: Optional[Dict[str, Any]] = {}
    is_enabled: Optional[bool] = True

class AutomationUpdateRequest(BaseModel):
    name: Optional[str] = None
    automation_type: Optional[str] = None
    trigger_type: Optional[str] = None
    trigger_value: Optional[str] = None
    action_type: Optional[str] = None
    action_payload: Optional[Dict[str, Any]] = None
    is_enabled: Optional[bool] = None

AUTOMATION_TEMPLATES = [
    {
        "id": "calendar_15min",
        "name": "⏰ Lembrete de Agenda no Telegram (15min antes)",
        "description": "Verifica sua Google Agenda e envia um aviso formatado no Telegram 15 minutos antes de cada compromisso começar.",
        "icon": "📅",
        "automation_type": "calendar_reminder",
        "trigger_type": "event_relative_minutes",
        "trigger_value": "15",
        "action_type": "telegram_alert",
        "action_payload": {"minutes_before": 15}
    },
    {
        "id": "calendar_30min",
        "name": "⏰ Lembrete de Agenda no Telegram (30min antes)",
        "description": "Envia um aviso no Telegram 30 minutos antes do início de qualquer compromisso agendado.",
        "icon": "📅",
        "automation_type": "calendar_reminder",
        "trigger_type": "event_relative_minutes",
        "trigger_value": "30",
        "action_type": "telegram_alert",
        "action_payload": {"minutes_before": 30}
    },
    {
        "id": "morning_briefing",
        "name": "☀️ Resumo Matinal Diário (08:00)",
        "description": "Envia no seu Telegram todos os dias às 08:00 o resumo completo de compromissos de hoje, tarefas pendentes e status da casa.",
        "icon": "☀️",
        "automation_type": "daily_summary",
        "trigger_type": "daily_time",
        "trigger_value": "08:00",
        "action_type": "telegram_alert",
        "action_payload": {}
    },
    {
        "id": "night_briefing",
        "name": "🌙 Resumo Noturno & Fechamento (21:00)",
        "description": "Envia no seu Telegram às 21:00 os compromissos de amanhã e pendências do dia.",
        "icon": "🌙",
        "automation_type": "daily_summary",
        "trigger_type": "daily_time",
        "trigger_value": "21:00",
        "action_type": "telegram_alert",
        "action_payload": {}
    },
    {
        "id": "night_lights_off",
        "name": "💡 Apagar Todas as Luzes às 23:30",
        "description": "Apaga automaticamente todas as lâmpadas da residência às 23:30 via comando MQTT.",
        "icon": "💡",
        "automation_type": "mqtt_schedule",
        "trigger_type": "daily_time",
        "trigger_value": "23:30",
        "action_type": "mqtt_command",
        "action_payload": {"room": "todas", "action": "OFF", "notify_telegram": True}
    },
    {
        "id": "porch_lights_on",
        "name": "💡 Ligar Luz Externa às 18:30",
        "description": "Liga as luzes externas/jardim às 18:30 todos os dias.",
        "icon": "💡",
        "automation_type": "mqtt_schedule",
        "trigger_type": "daily_time",
        "trigger_value": "18:30",
        "action_type": "mqtt_command",
        "action_payload": {"room": "externa", "action": "ON", "notify_telegram": True}
    },
    {
        "id": "custom_agent_task",
        "name": "🤖 Tarefa Inteligente Personalizada",
        "description": "Executa periodicamente uma instrução em linguagem natural pelo agente e envia a resposta ao Telegram.",
        "icon": "🤖",
        "automation_type": "custom_prompt",
        "trigger_type": "interval_minutes",
        "trigger_value": "60",
        "action_type": "agent_prompt",
        "action_payload": {"prompt": "Verifique se tenho e-mails importantes não lidos ou tarefas urgentes"}
    },
    {
        "id": "video_resident_find",
        "name": "📹 Reconhecer Morador na Câmera & Avisar no Telegram",
        "description": "Monitora a câmera com visão computacional e IA. Ao reconhecer o morador cadastrado, envia aviso e a foto capturada instantaneamente no Telegram.",
        "icon": "👤",
        "automation_type": "video_face_recognition",
        "trigger_type": "interval_seconds",
        "trigger_value": "30",
        "action_type": "video_alert",
        "action_payload": {
            "detection_mode": "video_face_recognition",
            "target_person": "todos",
            "notify_telegram": True,
            "cooldown_seconds": 300,
            "custom_message": "🎉 Morador identificado na câmera da residência!"
        }
    },
    {
        "id": "video_unknown_person_alert",
        "name": "🚨 Alerta de Segurança: Visitante / Pessoa Não Cadastrada",
        "description": "Analisa a câmera e envia um alerta imediato com a foto no Telegram se detectar uma pessoa não cadastrada nos moradores da casa.",
        "icon": "🚨",
        "automation_type": "video_unknown_alert",
        "trigger_type": "interval_seconds",
        "trigger_value": "30",
        "action_type": "video_alert",
        "action_payload": {
            "detection_mode": "video_unknown_alert",
            "target_person": "desconhecido",
            "notify_telegram": True,
            "cooldown_seconds": 300,
            "custom_message": "🚨 Atenção: Pessoa não cadastrada/visitante detectada na câmera!"
        }
    },
    {
        "id": "video_welcome_arrival",
        "name": "🎉 Boas-Vindas Inteligente (Reconhecimento Facial + Luzes)",
        "description": "Ao reconhecer a chegada do morador, acende as luzes do cômodo via MQTT e envia mensagem de boas-vindas com foto no Telegram.",
        "icon": "✨",
        "automation_type": "video_face_recognition",
        "trigger_type": "interval_seconds",
        "trigger_value": "30",
        "action_type": "video_alert",
        "action_payload": {
            "detection_mode": "video_face_recognition",
            "target_person": "todos",
            "notify_telegram": True,
            "agent_action_prompt": "Acender a luz da sala e da entrada",
            "cooldown_seconds": 600,
            "custom_message": "🏠 Seja bem-vindo(a) de volta! Luzes acesas para sua chegada."
        }
    }
]

@app.get("/api/automations/templates")
def get_automation_templates_endpoint():
    """Retorna os modelos prontos de automações para fácil criação pelo usuário."""
    return {"templates": AUTOMATION_TEMPLATES}

@app.get("/api/residents/list")
def list_residents_endpoint(token_payload: dict = Depends(get_current_user_token)):
    """Retorna a lista de moradores cadastrados com indicação de fotos para automações."""
    residents = db_get_all_residents()
    res_list = []
    for r in residents:
        res_list.append({
            "name": r.get("name", "Morador"),
            "email": r.get("email", ""),
            "has_photo": bool(r.get("has_photo")),
            "photo_preview": r.get("photo_base64", "")[:120] if r.get("has_photo") else ""
        })
    return {"residents": res_list}

@app.get("/api/automations")
def list_user_automations_endpoint(token_payload: dict = Depends(get_current_user_token)):
    """Lista todas as automações salvas para o usuário logado."""
    user_email = token_payload.get("sub", "")
    if not user_email:
        raise HTTPException(status_code=401, detail="Usuário não autenticado.")
    automations = db_get_automations(user_email)
    counts = db_get_automations_count(user_email)
    return {
        "automations": automations,
        "counts": counts,
        "engine_running": automation_engine.is_running()
    }

@app.post("/api/automations")
def create_user_automation_endpoint(
    req: AutomationCreateRequest,
    token_payload: dict = Depends(get_current_user_token)
):
    """Cria uma nova regra de automação no SQLite."""
    user_email = token_payload.get("sub", "")
    if not user_email:
        raise HTTPException(status_code=401, detail="Usuário não autenticado.")
        
    created = db_create_automation(
        user_email=user_email,
        name=req.name,
        automation_type=req.automation_type,
        trigger_type=req.trigger_type,
        trigger_value=req.trigger_value,
        action_type=req.action_type,
        action_payload=req.action_payload,
        is_enabled=req.is_enabled if req.is_enabled is not None else True
    )
    return {"status": "success", "automation": created}

@app.get("/api/automations/{auto_id}")
def get_user_automation_endpoint(
    auto_id: int,
    token_payload: dict = Depends(get_current_user_token)
):
    user_email = token_payload.get("sub", "")
    auto = db_get_automation_by_id(user_email, auto_id)
    if not auto:
        raise HTTPException(status_code=404, detail="Automação não encontrada.")
    return {"status": "success", "automation": auto}

@app.put("/api/automations/{auto_id}")
def update_user_automation_endpoint(
    auto_id: int,
    req: AutomationUpdateRequest,
    token_payload: dict = Depends(get_current_user_token)
):
    user_email = token_payload.get("sub", "")
    data = req.dict(exclude_unset=True)
    updated = db_update_automation(user_email, auto_id, data)
    if not updated:
        raise HTTPException(status_code=404, detail="Automação não encontrada.")
    return {"status": "success", "automation": updated}

@app.delete("/api/automations/{auto_id}")
def delete_user_automation_endpoint(
    auto_id: int,
    token_payload: dict = Depends(get_current_user_token)
):
    user_email = token_payload.get("sub", "")
    deleted = db_delete_automation(user_email, auto_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Automação não encontrada.")
    return {"status": "success", "deleted": True}

@app.patch("/api/automations/{auto_id}/toggle")
def toggle_user_automation_endpoint(
    auto_id: int,
    token_payload: dict = Depends(get_current_user_token)
):
    user_email = token_payload.get("sub", "")
    toggled = db_toggle_automation(user_email, auto_id)
    if not toggled:
        raise HTTPException(status_code=404, detail="Automação não encontrada.")
    return {"status": "success", "automation": toggled}

@app.post("/api/automations/{auto_id}/run")
def run_user_automation_endpoint(
    auto_id: int,
    token_payload: dict = Depends(get_current_user_token)
):
    """Executa a automação imediatamente para teste pelo usuário."""
    user_email = token_payload.get("sub", "")
    ok, msg = run_automation_now(auto_id, user_email)
    return {
        "status": "success" if ok else "error",
        "executed": ok,
        "message": msg
    }

# =========================================================================
# SÍNTESE DE VOZ NEURAL HUMANA (TTS)
# =========================================================================

class TTSRequest(BaseModel):
    text: str
    voice: Optional[str] = "pt-BR-FranciscaNeural"
    rate: Optional[str] = "+0%"
    pitch: Optional[str] = "+0Hz"

@app.get("/api/tts/voices")
def get_tts_voices():
    """Retorna as vozes neurais humanas disponíveis em português e seus perfis"""
    return {
        "voices": [
            {
                "id": "pt-BR-FranciscaNeural",
                "name": "Francisca (Feminina - Suave e Acolhedora)",
                "gender": "Female",
                "recommended": True,
                "description": "Voz neural acolhedora, tom natural e extremamente humana"
            },
            {
                "id": "pt-BR-ThalitaMultilingualNeural",
                "name": "Thalita (Feminina - Jovem e Dinâmica)",
                "gender": "Female",
                "recommended": False,
                "description": "Voz jovem, expressiva e moderna"
            },
            {
                "id": "pt-BR-AntonioNeural",
                "name": "Antonio (Masculina - Natural e Confiante)",
                "gender": "Male",
                "recommended": False,
                "description": "Voz masculina equilibrada e clara"
            },
            {
                "id": "browser-native",
                "name": "Voz do Navegador (Offline)",
                "gender": "Auto",
                "recommended": False,
                "description": "Utiliza o sintetizador nativo do próprio navegador"
            }
        ]
    }

_TTS_CACHE: Dict[str, bytes] = {}

def get_tts_cache_key(text: str, voice: str, rate: str, pitch: str) -> str:
    return f"{voice}:{rate}:{pitch}:{text.strip()}"

async def _synthesize_edge_tts_bytes(text: str, voice: str, rate: str = "+0%", pitch: str = "+0Hz") -> bytes:
    communicate = edge_tts.Communicate(
        text.strip(),
        voice=voice or "pt-BR-FranciscaNeural",
        rate=rate or "+0%",
        pitch=pitch or "+0Hz"
    )
    audio_stream = io.BytesIO()
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_stream.write(chunk["data"])
    return audio_stream.getvalue()

def prewarm_tts_cache_background():
    """Pré-aquece em segundo plano o cache de áudio das mensagens de status mais comuns."""
    def worker():
        try:
            from api.agent import TOOL_STATUS_MESSAGES
            phrases = list(set(list(TOOL_STATUS_MESSAGES.values()) + [
                "Analisando sua solicitação...",
                "Processando as informações para responder você...",
                "Só um momento, verificando...",
                "Aguarde um instante..."
            ]))
            voices = ["pt-BR-FranciscaNeural", "pt-BR-AntonioNeural"]
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            for phrase in phrases:
                for v in voices:
                    for r in ["+0%", "+10%", "+12%", "+15%"]:
                        key = get_tts_cache_key(phrase, v, r, "+0Hz")
                        if key not in _TTS_CACHE:
                            try:
                                audio_bytes = loop.run_until_complete(_synthesize_edge_tts_bytes(phrase, v, rate=r))
                                _TTS_CACHE[key] = audio_bytes
                            except Exception:
                                pass
            loop.close()
            system_logger.info(f"Cache de áudio TTS pré-aquecido ({len(_TTS_CACHE)} áudios em RAM prontos para resposta instantânea).")
        except Exception as e:
            system_logger.warning(f"Aviso no pré-aquecimento de TTS: {e}")

    threading.Thread(target=worker, daemon=True).start()

@app.post("/api/tts")
async def generate_tts(request: TTSRequest):
    """Gera áudio MP3 de alta fidelidade com voz neural humana via Edge-TTS com cache ultra rápido"""
    if not request.text or not request.text.strip():
        raise HTTPException(status_code=400, detail="Texto para síntese de voz não pode ser vazio.")
    
    clean_text = request.text.strip()
    voice = request.voice or "pt-BR-FranciscaNeural"
    rate = request.rate or "+0%"
    pitch = request.pitch or "+0Hz"
    cache_key = get_tts_cache_key(clean_text, voice, rate, pitch)
    
    # Retorna do cache em memória instantaneamente (~1ms)
    if cache_key in _TTS_CACHE:
        return StreamingResponse(io.BytesIO(_TTS_CACHE[cache_key]), media_type="audio/mpeg")
    
    try:
        audio_bytes = await _synthesize_edge_tts_bytes(clean_text, voice, rate, pitch)
        if len(_TTS_CACHE) < 1000:
            _TTS_CACHE[cache_key] = audio_bytes
        
        return StreamingResponse(io.BytesIO(audio_bytes), media_type="audio/mpeg")
    except Exception as e:
        system_logger.error(f"Erro na geração de áudio TTS ({voice}): {e}")
        raise HTTPException(status_code=500, detail=f"Erro na síntese de voz: {str(e)}")

# =========================================================================
# ROTAS ESTÁTICAS E FRONTEND
# =========================================================================

# Montar pasta static
static_dir = Path(__file__).parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Montar pasta config
config_dir = project_root / "config"
if not config_dir.exists():
    config_dir = current_dir / "config"

if config_dir.exists():
    app.mount("/config", StaticFiles(directory=config_dir), name="config")

@app.get("/login")
@app.get("/login.html")
def serve_login():
    path = static_dir / "login.html"
    if path.exists():
        return FileResponse(path)
    return {"message": "Login page"}

@app.get("/register")
@app.get("/register.html")
def serve_register():
    path = static_dir / "register.html"
    if path.exists():
        return FileResponse(path)
    return {"message": "Register page"}

@app.get("/profile")
@app.get("/profile.html")
def serve_profile():
    path = static_dir / "profile.html"
    if not path.exists():
        path = current_dir / "profile.html"
    if path.exists():
        return FileResponse(path)
    return {"message": "Profile page"}

@app.get("/casa")
@app.get("/casa.html")
def serve_casa():
    path = static_dir / "casa.html"
    if not path.exists():
        path = current_dir / "casa.html"
    if path.exists():
        return FileResponse(path)
    return {"message": "Casa page"}

@app.get("/guide_modal.js")
def serve_guide_modal_js():
    path = static_dir / "guide_modal.js"
    if not path.exists():
        path = current_dir / "guide_modal.js"
    if path.exists():
        return FileResponse(path, media_type="application/javascript")
    return {"message": "Guide script"}

@app.get("/agent")
@app.get("/agent.html")
@app.get("/")
def serve_index():
    index_path = static_dir / "index.html"
    if not index_path.exists():
        index_path = current_dir / "index.html"
    if index_path.exists():
        return FileResponse(index_path)
    return {"message": "Smart Home API rodando."}

if __name__ == "__main__":
    import uvicorn
    system_logger.info("Iniciando servidor Uvicorn na porta 8000...")
    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True)

import os
import json
import sqlite3
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Tuple

try:
    from api.logger import system_logger
except ImportError:
    from logger import system_logger

DB_PATH = Path(__file__).parent / "smarthome.db"

def get_db_connection() -> sqlite3.Connection:
    """Cria e retorna uma conexão com o banco de dados SQLite."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Inicializa as tabelas do banco de dados SQLite."""
    system_logger.info(f"Inicializando banco de dados SQLite em: {DB_PATH}")
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Tabela de Usuários
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            phone TEXT,
            email TEXT UNIQUE NOT NULL,
            hashed_password TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    
    # Tabela de Perfil e Memória do Usuário
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_email TEXT UNIQUE NOT NULL,
            blood_type TEXT DEFAULT '',
            favorite_movies TEXT DEFAULT '',
            favorite_foods TEXT DEFAULT '',
            favorite_music TEXT DEFAULT '',
            favorite_places TEXT DEFAULT '',
            car_info TEXT DEFAULT '',
            allergies_health TEXT DEFAULT '',
            personal_notes TEXT DEFAULT '',
            photo_base64 TEXT DEFAULT '',
            gmail_email TEXT DEFAULT '',
            gmail_app_password TEXT DEFAULT '',
            camera_type TEXT DEFAULT 'device',
            camera_ip_url TEXT DEFAULT '',
            camera_username TEXT DEFAULT '',
            camera_password TEXT DEFAULT '',
            camera_auto_greeting INTEGER DEFAULT 1,
            camera_device_index INTEGER DEFAULT 0,
            telegram_bot_token TEXT DEFAULT '',
            telegram_chat_id TEXT DEFAULT '',
            telegram_enabled INTEGER DEFAULT 0,
            telegram_notify_camera INTEGER DEFAULT 1,
            telegram_notify_tasks INTEGER DEFAULT 1,
            api_key TEXT DEFAULT '',
            ai_model TEXT DEFAULT 'gemini-2.5-flash-lite',
            agent_name TEXT DEFAULT 'Sexta-Feira',
            voice TEXT DEFAULT 'pt-BR-FranciscaNeural',
            system_commands_enabled INTEGER DEFAULT 0,
            updated_at TEXT NOT NULL
        )
    """)

    # Migração automática de colunas para bancos existentes
    for col_name, col_def in [
        ("photo_base64", "TEXT DEFAULT ''"),
        ("gmail_email", "TEXT DEFAULT ''"),
        ("gmail_app_password", "TEXT DEFAULT ''"),
        ("camera_type", "TEXT DEFAULT 'device'"),
        ("camera_ip_url", "TEXT DEFAULT ''"),
        ("camera_username", "TEXT DEFAULT ''"),
        ("camera_password", "TEXT DEFAULT ''"),
        ("camera_auto_greeting", "INTEGER DEFAULT 1"),
        ("camera_device_index", "INTEGER DEFAULT 0"),
        ("telegram_bot_token", "TEXT DEFAULT ''"),
        ("telegram_chat_id", "TEXT DEFAULT ''"),
        ("telegram_enabled", "INTEGER DEFAULT 0"),
        ("telegram_notify_camera", "INTEGER DEFAULT 1"),
        ("telegram_notify_tasks", "INTEGER DEFAULT 1"),
        ("api_key", "TEXT DEFAULT ''"),
        ("ai_model", "TEXT DEFAULT 'gemini-2.5-flash-lite'"),
        ("agent_name", "TEXT DEFAULT 'Sexta-Feira'"),
        ("voice", "TEXT DEFAULT 'pt-BR-FranciscaNeural'"),
        ("system_commands_enabled", "INTEGER DEFAULT 0")
    ]:
        try:
            cursor.execute(f"ALTER TABLE user_profiles ADD COLUMN {col_name} {col_def}")
        except Exception:
            pass

    # Tabela de Histórico e Memória de Conversas
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_email TEXT NOT NULL,
            user_message TEXT NOT NULL,
            agent_response TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_chat_history_user 
        ON chat_history(user_email, id DESC)
    """)

    # Tabela de Cache Local dos Contatos do Google
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS google_contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_email TEXT NOT NULL,
            uid TEXT NOT NULL,
            href TEXT NOT NULL,
            name TEXT NOT NULL,
            phones TEXT DEFAULT '',
            emails TEXT DEFAULT '',
            notes TEXT DEFAULT '',
            updated_at TEXT NOT NULL,
            UNIQUE(user_email, uid)
        )
    """)

    # Tabela de Tarefas e Lembretes (To-Do)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_email TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            due_date TEXT DEFAULT '',
            due_time TEXT DEFAULT '',
            priority TEXT DEFAULT 'media',
            status TEXT DEFAULT 'pendente',
            calendar_event_uid TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            completed_at TEXT DEFAULT ''
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_user_tasks_status
        ON user_tasks(user_email, status, due_date)
    """)

    # Tabela de Notas e Listas de Compras (Estilo Google Keep)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_email TEXT NOT NULL,
            title TEXT NOT NULL,
            content TEXT DEFAULT '',
            note_type TEXT DEFAULT 'texto',
            color TEXT DEFAULT 'padrao',
            is_pinned INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_user_notes_user
        ON user_notes(user_email, is_pinned DESC, id DESC)
    """)

    # Tabela de Itens de Checklist (para Listas de Compras)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS note_checklist_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            note_id INTEGER NOT NULL,
            item_text TEXT NOT NULL,
            is_completed INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY (note_id) REFERENCES user_notes(id) ON DELETE CASCADE
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_checklist_items_note
        ON note_checklist_items(note_id, is_completed)
    """)

    # Tabela de Automações & Agendamentos em Segundo Plano
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_automations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_email TEXT NOT NULL,
            name TEXT NOT NULL,
            automation_type TEXT NOT NULL,
            trigger_type TEXT NOT NULL,
            trigger_value TEXT NOT NULL,
            action_type TEXT NOT NULL,
            action_payload TEXT DEFAULT '{}',
            is_enabled INTEGER DEFAULT 1,
            last_run_at TEXT DEFAULT '',
            last_status TEXT DEFAULT 'pending',
            last_result TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_user_automations_user
        ON user_automations(user_email, is_enabled)
    """)

    # Tabela de Deduplicação de Eventos Notificados
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS automation_notified_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            automation_id INTEGER NOT NULL,
            user_email TEXT NOT NULL,
            event_key TEXT NOT NULL,
            notified_at TEXT NOT NULL,
            UNIQUE(automation_id, event_key)
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_notified_events_lookup
        ON automation_notified_events(automation_id, event_key)
    """)

    # Tabela de Configuração da Casa (MQTT e Cômodos)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_house_configs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_email TEXT UNIQUE NOT NULL,
            broker TEXT DEFAULT 'test.mosquitto.org',
            port TEXT DEFAULT '8080',
            topic_prefix TEXT DEFAULT 'pensador/casa',
            rooms_json TEXT DEFAULT '[]',
            updated_at TEXT NOT NULL
        )
    """)

    # Tabela de Memória de Longo Prazo e Aprendizado Autônomo do Agente
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS agent_long_term_memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_email TEXT NOT NULL,
            fact TEXT NOT NULL,
            category TEXT DEFAULT 'geral',
            importance INTEGER DEFAULT 3,
            context TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_accessed_at TEXT DEFAULT ''
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_agent_memories_user
        ON agent_long_term_memories(user_email, importance DESC, id DESC)
    """)

    # Tabela de Múltiplas Câmeras (Webcam Local e Câmeras IP/RTSP/ESP32)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_cameras (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_email TEXT NOT NULL,
            name TEXT NOT NULL,
            camera_type TEXT NOT NULL,        -- 'device' ou 'ip'
            camera_ip_url TEXT DEFAULT '',
            camera_username TEXT DEFAULT '',
            camera_password TEXT DEFAULT '',
            camera_device_index INTEGER DEFAULT 0,
            is_default INTEGER DEFAULT 0,
            enabled INTEGER DEFAULT 1,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_user_cameras_user 
        ON user_cameras(user_email, is_default DESC, id ASC)
    """)
    
    conn.commit()
    conn.close()
    system_logger.info("Tabelas do banco de dados verificadas/criadas com sucesso.")

def get_user_profile(user_email: str) -> Dict[str, Any]:
    """Recupera o perfil do usuário pelo e-mail."""
    if not user_email:
        return {}
    clean_email = user_email.strip().lower()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM user_profiles WHERE user_email = ?", (clean_email,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return {
        "user_email": clean_email,
        "blood_type": "",
        "favorite_movies": "",
        "favorite_foods": "",
        "favorite_music": "",
        "favorite_places": "",
        "car_info": "",
        "allergies_health": "",
        "personal_notes": "",
        "photo_base64": "",
        "gmail_email": "",
        "gmail_app_password": "",
        "camera_type": "device",
        "camera_ip_url": "",
        "camera_username": "",
        "camera_password": "",
        "camera_auto_greeting": 1,
        "camera_device_index": 0,
        "telegram_bot_token": "",
        "telegram_chat_id": "",
        "telegram_enabled": 0,
        "telegram_notify_camera": 1,
        "telegram_notify_tasks": 1,
        "api_key": "",
        "ai_model": "gemini-2.5-flash-lite",
        "voice": "pt-BR-FranciscaNeural",
        "updated_at": ""
    }

def save_user_profile(user_email: str, profile_data: Dict[str, Any]) -> Dict[str, Any]:
    """Salva ou atualiza os dados do perfil do usuário no SQLite."""
    clean_email = user_email.strip().lower()
    updated_at = datetime.now(timezone.utc).isoformat()
    
    current = get_user_profile(clean_email)
    photo_base64 = profile_data.get("photo_base64", current.get("photo_base64", "")) or ""
    gmail_email = profile_data.get("gmail_email", current.get("gmail_email", "")) or ""
    gmail_app_pwd = profile_data.get("gmail_app_password", current.get("gmail_app_password", "")) or ""
    camera_type = profile_data.get("camera_type", current.get("camera_type", "device")) or "device"
    camera_ip_url = profile_data.get("camera_ip_url", current.get("camera_ip_url", "")) or ""
    camera_username = profile_data.get("camera_username", current.get("camera_username", "")) or ""
    camera_password = profile_data.get("camera_password", current.get("camera_password", "")) or ""
    camera_auto_greeting = profile_data.get("camera_auto_greeting", current.get("camera_auto_greeting", 1))
    camera_device_index = profile_data.get("camera_device_index", current.get("camera_device_index", 0))
    
    telegram_bot_token = profile_data.get("telegram_bot_token", current.get("telegram_bot_token", "")) or ""
    telegram_chat_id = profile_data.get("telegram_chat_id", current.get("telegram_chat_id", "")) or ""
    telegram_enabled = profile_data.get("telegram_enabled", current.get("telegram_enabled", 0))
    telegram_notify_camera = profile_data.get("telegram_notify_camera", current.get("telegram_notify_camera", 1))
    telegram_notify_tasks = profile_data.get("telegram_notify_tasks", current.get("telegram_notify_tasks", 1))
    
    api_key = profile_data.get("api_key", current.get("api_key", "")) or ""
    ai_model = profile_data.get("ai_model", current.get("ai_model", "gemini-2.5-flash-lite")) or "gemini-2.5-flash-lite"
    voice = profile_data.get("voice", current.get("voice", "pt-BR-FranciscaNeural")) or "pt-BR-FranciscaNeural"
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO user_profiles (
            user_email, blood_type, favorite_movies, favorite_foods, 
            favorite_music, favorite_places, car_info, allergies_health, 
            personal_notes, photo_base64, gmail_email, gmail_app_password, 
            camera_type, camera_ip_url, camera_username, camera_password,
            camera_auto_greeting, camera_device_index,
            telegram_bot_token, telegram_chat_id, telegram_enabled,
            telegram_notify_camera, telegram_notify_tasks,
            api_key, ai_model, voice,
            updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_email) DO UPDATE SET
            blood_type=excluded.blood_type,
            favorite_movies=excluded.favorite_movies,
            favorite_foods=excluded.favorite_foods,
            favorite_music=excluded.favorite_music,
            favorite_places=excluded.favorite_places,
            car_info=excluded.car_info,
            allergies_health=excluded.allergies_health,
            personal_notes=excluded.personal_notes,
            photo_base64=excluded.photo_base64,
            gmail_email=excluded.gmail_email,
            gmail_app_password=excluded.gmail_app_password,
            camera_type=excluded.camera_type,
            camera_ip_url=excluded.camera_ip_url,
            camera_username=excluded.camera_username,
            camera_password=excluded.camera_password,
            camera_auto_greeting=excluded.camera_auto_greeting,
            camera_device_index=excluded.camera_device_index,
            telegram_bot_token=excluded.telegram_bot_token,
            telegram_chat_id=excluded.telegram_chat_id,
            telegram_enabled=excluded.telegram_enabled,
            telegram_notify_camera=excluded.telegram_notify_camera,
            telegram_notify_tasks=excluded.telegram_notify_tasks,
            api_key=excluded.api_key,
            ai_model=excluded.ai_model,
            voice=excluded.voice,
            updated_at=excluded.updated_at
    """, (
        clean_email,
        profile_data.get("blood_type", current.get("blood_type", "")) or "",
        profile_data.get("favorite_movies", current.get("favorite_movies", "")) or "",
        profile_data.get("favorite_foods", current.get("favorite_foods", "")) or "",
        profile_data.get("favorite_music", current.get("favorite_music", "")) or "",
        profile_data.get("favorite_places", current.get("favorite_places", "")) or "",
        profile_data.get("car_info", current.get("car_info", "")) or "",
        profile_data.get("allergies_health", current.get("allergies_health", "")) or "",
        profile_data.get("personal_notes", current.get("personal_notes", "")) or "",
        photo_base64,
        gmail_email,
        gmail_app_pwd,
        camera_type,
        camera_ip_url,
        camera_username,
        camera_password,
        1 if camera_auto_greeting else 0,
        int(camera_device_index or 0),
        telegram_bot_token.strip(),
        str(telegram_chat_id).strip(),
        1 if telegram_enabled else 0,
        1 if telegram_notify_camera else 0,
        1 if telegram_notify_tasks else 0,
        api_key.strip(),
        ai_model.strip(),
        voice.strip(),
        updated_at
    ))
    
    conn.commit()
    conn.close()
    system_logger.info(f"Perfil atualizado no SQLite para o usuário: {clean_email}")
    return get_user_profile(clean_email)

def db_save_user_photo(user_email: str, photo_base64: str) -> Dict[str, Any]:
    """Salva a foto de perfil/referência facial do usuário no SQLite."""
    clean_email = (user_email or "").strip().lower()
    current = get_user_profile(clean_email)
    current["photo_base64"] = (photo_base64 or "").strip()
    return save_user_profile(clean_email, current)

def db_get_user_photo(user_email: str) -> str:
    """Recupera a foto de perfil em base64 do usuário."""
    clean_email = (user_email or "").strip().lower()
    prof = get_user_profile(clean_email)
    return prof.get("photo_base64", "") or ""

def db_get_all_residents() -> List[Dict[str, Any]]:
    """Retorna a lista de todos os moradores cadastrados no sistema com suas fotos de referência."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT 
            u.id as user_id,
            u.name as name,
            u.email as email,
            p.photo_base64 as photo_base64,
            p.personal_notes as personal_notes,
            p.blood_type as blood_type
        FROM users u
        LEFT JOIN user_profiles p ON LOWER(u.email) = LOWER(p.user_email)
        ORDER BY u.id ASC
    """)
    rows = cursor.fetchall()
    conn.close()
    residents = []
    for r in rows:
        photo = r["photo_base64"] or ""
        residents.append({
            "user_id": r["user_id"],
            "name": r["name"] or r["email"].split("@")[0].capitalize(),
            "email": r["email"],
            "has_photo": bool(photo and len(photo) > 50),
            "photo_base64": photo,
            "personal_notes": r["personal_notes"] or "",
            "blood_type": r["blood_type"] or ""
        })
    return residents

def db_save_google_credentials(user_email: str, gmail_email: str, gmail_app_password: str) -> Dict[str, Any]:
    """Salva o e-mail do Gmail e a senha de aplicativo Google do usuário no SQLite."""
    clean_email = (user_email or "").strip().lower()
    clean_gmail = (gmail_email or "").strip().lower()
    clean_pwd = (gmail_app_password or "").replace(" ", "").strip()
    is_masked = bool("*" in clean_pwd or "•" in clean_pwd)
    updated_at = datetime.now(timezone.utc).isoformat()
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Se a senha informada for mascarada ou vazia, preserva a senha existente no banco
    if (not clean_pwd or is_masked) and clean_email:
        cursor.execute("SELECT gmail_app_password FROM user_profiles WHERE user_email = ?", (clean_email,))
        row = cursor.fetchone()
        if row and row["gmail_app_password"]:
            clean_pwd = row["gmail_app_password"].strip()
            
    cursor.execute("""
        INSERT INTO user_profiles (user_email, gmail_email, gmail_app_password, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(user_email) DO UPDATE SET
            gmail_email=excluded.gmail_email,
            gmail_app_password=excluded.gmail_app_password,
            updated_at=excluded.updated_at
    """, (clean_email, clean_gmail, clean_pwd, updated_at))
    conn.commit()
    conn.close()
    system_logger.info(f"Credenciais Google salvas para o usuário: {clean_email} (Gmail: {clean_gmail})")
    return {"gmail_email": clean_gmail, "configured": bool(clean_gmail and clean_pwd)}

def db_get_google_credentials(user_email: str) -> Tuple[str, str]:
    """
    Retorna (gmail_email, gmail_app_password) para o usuário.
    Se não configurado no perfil, faz fallback para as variáveis do ambiente (.env).
    """
    clean_email = (user_email or "").strip().lower()
    if clean_email:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT gmail_email, gmail_app_password FROM user_profiles WHERE user_email = ?", (clean_email,))
        row = cursor.fetchone()
        conn.close()
        if row:
            db_gmail = (row["gmail_email"] or "").strip()
            db_pwd = (row["gmail_app_password"] or "").replace(" ", "").strip()
            if db_gmail and db_pwd:
                return db_gmail, db_pwd
                
    # Fallback para .env
    env_email = (os.getenv("GMAIL_EMAIL") or os.getenv("GMAIL_USER") or "").strip()
    env_pwd = (os.getenv("GMAIL_APP_PASSWORD") or os.getenv("GMAIL_PASSWORD") or "").replace(" ", "").strip()
    return env_email, env_pwd

# =========================================================================
# CONFIGURAÇÃO DE MÚLTIPLAS CÂMERAS (LOCAL & IP) NO SQLITE
# =========================================================================

def _migrate_user_cameras_if_needed(cursor: sqlite3.Cursor, user_email: str):
    """Garante que o usuário tenha pelo menos uma câmera cadastrada, migrando do perfil legado se aplicável."""
    clean_email = (user_email or "").strip().lower()
    if not clean_email:
        return
        
    cursor.execute("SELECT COUNT(*) AS cnt FROM user_cameras WHERE user_email = ?", (clean_email,))
    row = cursor.fetchone()
    if row and row["cnt"] > 0:
        return
        
    # Verifica perfil legado para migração
    cursor.execute("""
        SELECT camera_type, camera_ip_url, camera_username, camera_password, camera_device_index 
        FROM user_profiles WHERE user_email = ?
    """, (clean_email,))
    prof = cursor.fetchone()
    
    now_iso = datetime.now(timezone.utc).isoformat()
    if prof and (prof["camera_ip_url"] or prof["camera_type"] == "ip"):
        cam_type = "ip"
        cam_url = (prof["camera_ip_url"] or "").strip()
        cam_user = (prof["camera_username"] or "").strip()
        cam_pwd = (prof["camera_password"] or "").strip()
        cam_idx = 0
        name = "Câmera IP Principal"
    else:
        cam_type = "device"
        cam_url = ""
        cam_user = ""
        cam_pwd = ""
        cam_idx = int(prof["camera_device_index"] or 0) if prof else 0
        name = "Câmera Local (Webcam)"

    cursor.execute("""
        INSERT INTO user_cameras (
            user_email, name, camera_type, camera_ip_url, camera_username, 
            camera_password, camera_device_index, is_default, enabled, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, 1, 1, ?, ?)
    """, (clean_email, name, cam_type, cam_url, cam_user, cam_pwd, cam_idx, now_iso, now_iso))
    system_logger.info(f"Auto-migração de câmera executada para usuário: {clean_email} -> {name}")

def db_get_user_cameras(user_email: str) -> List[Dict[str, Any]]:
    """Retorna todas as câmeras cadastradas pelo usuário."""
    clean_email = (user_email or "").strip().lower()
    if not clean_email:
        return []
        
    conn = get_db_connection()
    cursor = conn.cursor()
    _migrate_user_cameras_if_needed(cursor, clean_email)
    conn.commit()
    
    cursor.execute("""
        SELECT id, user_email, name, camera_type, camera_ip_url, camera_username, 
               camera_password, camera_device_index, is_default, enabled, created_at, updated_at
        FROM user_cameras 
        WHERE user_email = ?
        ORDER BY is_default DESC, id ASC
    """, (clean_email,))
    rows = cursor.fetchall()
    conn.close()
    
    cameras = []
    for r in rows:
        cameras.append({
            "id": r["id"],
            "user_email": r["user_email"],
            "name": r["name"],
            "camera_type": r["camera_type"] or "device",
            "camera_ip_url": r["camera_ip_url"] or "",
            "camera_username": r["camera_username"] or "",
            "camera_password": r["camera_password"] or "",
            "camera_device_index": int(r["camera_device_index"] or 0),
            "is_default": bool(r["is_default"]),
            "enabled": bool(r["enabled"]),
            "created_at": r["created_at"],
            "updated_at": r["updated_at"]
        })
    return cameras

def db_get_camera_by_id_or_name(user_email: str, identifier: Any = None) -> Optional[Dict[str, Any]]:
    """
    Busca uma câmera do usuário pelo ID, nome aproximado (ex: 'sala', 'garagem', 'externa', 'câmera 1') 
    ou retorna a câmera padrão se o identificador estiver vazio/padrão.
    """
    clean_email = (user_email or "").strip().lower()
    cameras = db_get_user_cameras(clean_email)
    if not cameras:
        return None
        
    if not identifier or str(identifier).strip().lower() in ["", "padrao", "padrão", "default", "todas"]:
        # Retorna a câmera padrão ou a primeira disponível
        for cam in cameras:
            if cam.get("is_default") and cam.get("enabled", True):
                return cam
        return cameras[0] if cameras else None
        
    ident_str = str(identifier).strip().lower()
    
    # 1. Se for numérico (ID ou índice)
    if ident_str.isdigit():
        target_id = int(ident_str)
        for cam in cameras:
            if cam["id"] == target_id:
                return cam
        # Se for número de 1 a N (ex: 'câmera 1')
        if 1 <= target_id <= len(cameras):
            return cameras[target_id - 1]
            
    # 2. Busca por padrão ordinal em texto (ex: "câmera 1", "câmera 2", "cam 3")
    import re
    ord_match = re.search(r'(?:câmera|camera|cam)\s*(\d+)', ident_str)
    if ord_match:
        idx = int(ord_match.group(1))
        if 1 <= idx <= len(cameras):
            return cameras[idx - 1]
            
    # 3. Busca por correspondência exata de nome (case-insensitive)
    for cam in cameras:
        if cam["name"].strip().lower() == ident_str:
            return cam
            
    # 4. Busca por correspondência parcial no nome (ex: "sala" encontra "Câmera da Sala")
    for cam in cameras:
        if ident_str in cam["name"].strip().lower() or cam["name"].strip().lower() in ident_str:
            return cam
            
    # Fallback: retorna a câmera padrão
    for cam in cameras:
        if cam.get("is_default"):
            return cam
    return cameras[0]

def db_save_user_camera(user_email: str, camera_data: Dict[str, Any]) -> Dict[str, Any]:
    """Cria ou atualiza uma câmera no banco SQLite para o usuário."""
    clean_email = (user_email or "").strip().lower()
    cam_id = camera_data.get("id")
    name = (camera_data.get("name") or "Nova Câmera").strip()
    cam_type = "ip" if (camera_data.get("camera_type") or "").strip().lower() == "ip" else "device"
    cam_url = (camera_data.get("camera_ip_url") or "").strip()
    cam_user = (camera_data.get("camera_username") or "").strip()
    cam_pwd = (camera_data.get("camera_password") or "").strip()
    cam_idx = int(camera_data.get("camera_device_index") or 0)
    is_default = 1 if camera_data.get("is_default") else 0
    enabled = 1 if camera_data.get("enabled", True) else 0
    now_iso = datetime.now(timezone.utc).isoformat()
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Se for a primeira câmera do usuário ou marcada como padrão
    cursor.execute("SELECT COUNT(*) as cnt FROM user_cameras WHERE user_email = ?", (clean_email,))
    existing_cnt = cursor.fetchone()["cnt"]
    if existing_cnt == 0:
        is_default = 1
        
    if is_default:
        cursor.execute("UPDATE user_cameras SET is_default = 0 WHERE user_email = ?", (clean_email,))
        
    if cam_id:
        cursor.execute("""
            UPDATE user_cameras 
            SET name = ?, camera_type = ?, camera_ip_url = ?, camera_username = ?,
                camera_password = CASE WHEN ? != '' THEN ? ELSE camera_password END,
                camera_device_index = ?, is_default = ?, enabled = ?, updated_at = ?
            WHERE id = ? AND user_email = ?
        """, (name, cam_type, cam_url, cam_user, cam_pwd, cam_pwd, cam_idx, is_default, enabled, now_iso, int(cam_id), clean_email))
        target_id = int(cam_id)
    else:
        cursor.execute("""
            INSERT INTO user_cameras (
                user_email, name, camera_type, camera_ip_url, camera_username, 
                camera_password, camera_device_index, is_default, enabled, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (clean_email, name, cam_type, cam_url, cam_user, cam_pwd, cam_idx, is_default, enabled, now_iso, now_iso))
        target_id = cursor.lastrowid

    # Sincroniza com perfil legado se for câmera padrão
    if is_default:
        cursor.execute("""
            UPDATE user_profiles 
            SET camera_type = ?, camera_ip_url = ?, camera_username = ?, 
                camera_password = CASE WHEN ? != '' THEN ? ELSE camera_password END,
                camera_device_index = ?, updated_at = ?
            WHERE user_email = ?
        """, (cam_type, cam_url, cam_user, cam_pwd, cam_pwd, cam_idx, now_iso, clean_email))

    conn.commit()
    conn.close()
    
    system_logger.info(f"Câmera salva com sucesso: ID {target_id} ('{name}', tipo: {cam_type}, padrão: {bool(is_default)}) para '{clean_email}'")
    return db_get_camera_by_id_or_name(clean_email, target_id) or {}

def db_delete_user_camera(user_email: str, camera_id: int) -> bool:
    """Remove uma câmera pelo ID e reatribui a padrão caso necessário."""
    clean_email = (user_email or "").strip().lower()
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT is_default FROM user_cameras WHERE id = ? AND user_email = ?", (int(camera_id), clean_email))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return False
        
    was_default = bool(row["is_default"])
    cursor.execute("DELETE FROM user_cameras WHERE id = ? AND user_email = ?", (int(camera_id), clean_email))
    
    # Se removeu a padrão, elege a primeira câmera restante como nova padrão
    if was_default:
        cursor.execute("SELECT id FROM user_cameras WHERE user_email = ? ORDER BY id ASC LIMIT 1", (clean_email,))
        first_rem = cursor.fetchone()
        if first_rem:
            cursor.execute("UPDATE user_cameras SET is_default = 1 WHERE id = ?", (first_rem["id"],))
            
    conn.commit()
    conn.close()
    system_logger.info(f"Câmera ID {camera_id} excluída para o usuário: {clean_email}")
    return True

def db_set_default_camera(user_email: str, camera_id: int) -> bool:
    """Define uma câmera específica como a padrão do usuário."""
    clean_email = (user_email or "").strip().lower()
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("SELECT id, camera_type, camera_ip_url, camera_username, camera_password, camera_device_index FROM user_cameras WHERE id = ? AND user_email = ?", (int(camera_id), clean_email))
    target = cursor.fetchone()
    if not target:
        conn.close()
        return False
        
    cursor.execute("UPDATE user_cameras SET is_default = 0 WHERE user_email = ?", (clean_email,))
    cursor.execute("UPDATE user_cameras SET is_default = 1 WHERE id = ? AND user_email = ?", (int(camera_id), clean_email))
    
    # Sincroniza com perfil legado
    now_iso = datetime.now(timezone.utc).isoformat()
    cursor.execute("""
        UPDATE user_profiles 
        SET camera_type = ?, camera_ip_url = ?, camera_username = ?, camera_password = ?,
            camera_device_index = ?, updated_at = ?
        WHERE user_email = ?
    """, (target["camera_type"], target["camera_ip_url"], target["camera_username"], target["camera_password"], target["camera_device_index"], now_iso, clean_email))
    
    conn.commit()
    conn.close()
    system_logger.info(f"Câmera ID {camera_id} definida como padrão para: {clean_email}")
    return True

def db_save_camera_config(
    user_email: str,
    camera_type: str = "device",
    camera_ip_url: str = "",
    camera_username: str = "",
    camera_password: str = "",
    camera_auto_greeting: bool = True,
    camera_device_index: int = 0
) -> Dict[str, Any]:
    """Salva a configuração da câmera padrão do usuário no SQLite (retrocompatibilidade)."""
    clean_email = (user_email or "").strip().lower()
    default_cam = db_get_camera_by_id_or_name(clean_email, "padrao")
    cam_id = default_cam.get("id") if default_cam else None
    
    data = {
        "id": cam_id,
        "name": default_cam.get("name", "Câmera Principal") if default_cam else "Câmera Principal",
        "camera_type": camera_type,
        "camera_ip_url": camera_ip_url,
        "camera_username": camera_username,
        "camera_password": camera_password,
        "camera_device_index": camera_device_index,
        "is_default": 1,
        "enabled": 1
    }
    db_save_user_camera(clean_email, data)
    
    # Atualiza flag de auto greeting no perfil
    conn = get_db_connection()
    c = conn.cursor()
    c.execute("UPDATE user_profiles SET camera_auto_greeting = ? WHERE user_email = ?", (1 if camera_auto_greeting else 0, clean_email))
    conn.commit()
    conn.close()
    
    return db_get_camera_config(clean_email)

def db_get_camera_config(user_email: str) -> Dict[str, Any]:
    """Retorna as configurações da câmera padrão para o usuário."""
    clean_email = (user_email or "").strip().lower()
    if clean_email:
        cam = db_get_camera_by_id_or_name(clean_email, "padrao")
        if cam:
            # Obtém flag de auto greeting
            conn = get_db_connection()
            c = conn.cursor()
            c.execute("SELECT camera_auto_greeting FROM user_profiles WHERE user_email = ?", (clean_email,))
            p_row = c.fetchone()
            conn.close()
            auto_greet = bool(p_row["camera_auto_greeting"]) if p_row else True
            
            return {
                "id": cam.get("id"),
                "name": cam.get("name", "Câmera Principal"),
                "camera_type": cam.get("camera_type", "device"),
                "camera_ip_url": cam.get("camera_ip_url", ""),
                "camera_username": cam.get("camera_username", ""),
                "camera_password": cam.get("camera_password", ""),
                "camera_auto_greeting": auto_greet,
                "camera_device_index": cam.get("camera_device_index", 0),
                "is_default": True
            }
            
    # Fallback para variáveis de ambiente ou padrão
    return {
        "name": "Câmera Local",
        "camera_type": os.getenv("CAMERA_TYPE", "device"),
        "camera_ip_url": os.getenv("CAMERA_IP_URL", ""),
        "camera_username": os.getenv("CAMERA_USERNAME", ""),
        "camera_password": os.getenv("CAMERA_PASSWORD", ""),
        "camera_auto_greeting": True,
        "camera_device_index": int(os.getenv("CAMERA_DEVICE_INDEX", "0")),
        "is_default": True
    }


# =========================================================================
# CONFIGURAÇÃO DO BOT DO TELEGRAM (SQLite)
# =========================================================================

def db_save_telegram_config(
    user_email: str,
    bot_token: str = "",
    chat_id: str = "",
    enabled: bool = True,
    notify_camera: bool = True,
    notify_tasks: bool = True
) -> Dict[str, Any]:
    """Salva a configuração do Bot do Telegram do usuário no SQLite."""
    clean_email = (user_email or "").strip().lower()
    clean_token = (bot_token or "").strip()
    clean_chat_id = str(chat_id or "").strip()
    is_enabled = 1 if enabled else 0
    notif_cam = 1 if notify_camera else 0
    notif_tsk = 1 if notify_tasks else 0
    updated_at = datetime.now(timezone.utc).isoformat()
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO user_profiles (
            user_email, telegram_bot_token, telegram_chat_id, telegram_enabled,
            telegram_notify_camera, telegram_notify_tasks, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_email) DO UPDATE SET
            telegram_bot_token=excluded.telegram_bot_token,
            telegram_chat_id=excluded.telegram_chat_id,
            telegram_enabled=excluded.telegram_enabled,
            telegram_notify_camera=excluded.telegram_notify_camera,
            telegram_notify_tasks=excluded.telegram_notify_tasks,
            updated_at=excluded.updated_at
    """, (clean_email, clean_token, clean_chat_id, is_enabled, notif_cam, notif_tsk, updated_at))
    conn.commit()
    conn.close()
    system_logger.info(f"Configuração do Telegram salva para o usuário: {clean_email} (Enabled: {enabled}, Chat ID: {clean_chat_id})")
    return db_get_telegram_config(clean_email)

def db_get_telegram_config(user_email: str) -> Dict[str, Any]:
    """Retorna as configurações do Telegram salvas para o usuário."""
    clean_email = (user_email or "").strip().lower()
    if clean_email:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT telegram_bot_token, telegram_chat_id, telegram_enabled,
                   telegram_notify_camera, telegram_notify_tasks
            FROM user_profiles WHERE user_email = ?
        """, (clean_email,))
        row = cursor.fetchone()
        conn.close()
        if row:
            token = (row["telegram_bot_token"] or "").strip()
            chat_id = (row["telegram_chat_id"] or "").strip()
            return {
                "bot_token": token,
                "chat_id": chat_id,
                "enabled": bool(row["telegram_enabled"]),
                "notify_camera": bool(row["telegram_notify_camera"]),
                "notify_tasks": bool(row["telegram_notify_tasks"]),
                "configured": bool(token and (row["telegram_enabled"] or chat_id))
            }
            
    # Fallback para .env
    env_token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    env_chat_id = (os.getenv("TELEGRAM_CHAT_ID") or "").strip()
    return {
        "bot_token": env_token,
        "chat_id": env_chat_id,
        "enabled": bool(env_token),
        "notify_camera": True,
        "notify_tasks": True,
        "configured": bool(env_token)
    }

def db_get_all_active_telegram_bots() -> List[Dict[str, Any]]:
    """Retorna todas as configurações de Telegram de usuários ativos para o serviço de long polling."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT u.id as user_id, COALESCE(u.name, 'Usuário') as user_name, 
               COALESCE(u.email, p.user_email) as user_email,
               p.telegram_bot_token as bot_token, p.telegram_chat_id as chat_id,
               p.telegram_enabled as enabled, p.telegram_notify_camera as notify_camera,
               p.telegram_notify_tasks as notify_tasks
        FROM user_profiles p
        LEFT JOIN users u ON LOWER(u.email) = LOWER(p.user_email)
        WHERE p.telegram_enabled = 1 AND LENGTH(TRIM(p.telegram_bot_token)) > 5
    """)
    rows = cursor.fetchall()
    conn.close()
    bots = []
    for r in rows:
        bots.append({
            "user_id": r["user_id"],
            "user_name": r["user_name"],
            "user_email": r["user_email"],
            "bot_token": r["bot_token"].strip(),
            "chat_id": (r["chat_id"] or "").strip(),
            "enabled": bool(r["enabled"]),
            "notify_camera": bool(r["notify_camera"]),
            "notify_tasks": bool(r["notify_tasks"])
        })
    return bots


# =========================================================================
# CONFIGURAÇÃO DE IA, API KEY E MODELO DO USUÁRIO (SQLite)
# =========================================================================

def db_save_ai_config(
    user_email: str,
    api_key: str = "",
    ai_model: str = "",
    voice: str = ""
) -> Dict[str, Any]:
    """Salva a chave de API (Gemini/OpenAI), modelo e voz do usuário no SQLite, preservando valores anteriores quando não enviados."""
def db_save_ai_config(
    user_email: str,
    api_key: str = "",
    ai_model: str = "",
    agent_name: str = "",
    voice: str = "",
    system_commands_enabled: Optional[bool] = None
) -> Dict[str, Any]:
    """Salva a chave de API, modelo de IA, nome do agente, voz do TTS e flag de comandos do sistema no perfil SQLite do usuário."""
    clean_email = (user_email or "").strip().lower()
    clean_key = (api_key or "").strip()
    clean_model = (ai_model or "").strip()
    clean_agent_name = (agent_name or "").strip()
    clean_voice = (voice or "").strip()
    updated_at = datetime.now(timezone.utc).isoformat()
    
    conn = get_db_connection()
    cursor = conn.cursor()

    # Prepara valor para system_commands_enabled
    sys_val = 1 if system_commands_enabled is True else (0 if system_commands_enabled is False else None)

    cursor.execute("""
        INSERT INTO user_profiles (
            user_email, api_key, ai_model, agent_name, voice, system_commands_enabled, updated_at
        )
        VALUES (
            ?, 
            ?, 
            COALESCE(NULLIF(?, ''), 'gemini-2.5-flash-lite'), 
            COALESCE(NULLIF(?, ''), 'Sexta-Feira'), 
            COALESCE(NULLIF(?, ''), 'pt-BR-FranciscaNeural'), 
            COALESCE(?, 0),
            ?
        )
        ON CONFLICT(user_email) DO UPDATE SET
            api_key=CASE WHEN ? != '' THEN ? ELSE api_key END,
            ai_model=CASE WHEN ? != '' THEN ? ELSE ai_model END,
            agent_name=CASE WHEN ? != '' THEN ? ELSE agent_name END,
            voice=CASE WHEN ? != '' THEN ? ELSE voice END,
            system_commands_enabled=CASE WHEN ? IS NOT NULL THEN ? ELSE system_commands_enabled END,
            updated_at=excluded.updated_at
    """, (
        clean_email, clean_key, clean_model, clean_agent_name, clean_voice, sys_val, updated_at,
        clean_key, clean_key,
        clean_model, clean_model,
        clean_agent_name, clean_agent_name,
        clean_voice, clean_voice,
        sys_val, sys_val
    ))
    conn.commit()
    conn.close()
    system_logger.info(f"Configuração de IA salva no SQLite para: {clean_email} (Modelo: {clean_model or 'mantido'}, Agente: {clean_agent_name or 'mantido'}, Voz: {clean_voice or 'mantida'}, Comandos Sistema: {system_commands_enabled})")
    return db_get_ai_config(clean_email)

def db_get_ai_config(user_email: str) -> Dict[str, Any]:
    """Retorna a configuração de IA (chave de API, modelo, nome do agente, voz e flag de comandos do sistema) do usuário."""
    clean_email = (user_email or "").strip().lower()
    if clean_email:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT api_key, ai_model, agent_name, voice, system_commands_enabled 
            FROM user_profiles WHERE user_email = ?
        """, (clean_email,))
        row = cursor.fetchone()
        conn.close()
        if row:
            stored_key = (row["api_key"] or "").strip()
            stored_model = (row["ai_model"] or "gemini-2.5-flash-lite").strip()
            stored_agent_name = (row["agent_name"] or "Sexta-Feira").strip() if "agent_name" in row.keys() else "Sexta-Feira"
            stored_voice = (row["voice"] or "pt-BR-FranciscaNeural").strip()
            stored_sys = bool(row["system_commands_enabled"]) if "system_commands_enabled" in row.keys() else False
            masked = f"{stored_key[:6]}...{stored_key[-4:]}" if len(stored_key) > 10 else ("Configurada" if stored_key else "")
            return {
                "api_key": stored_key,
                "masked_key": masked,
                "ai_model": stored_model,
                "agent_name": stored_agent_name or "Sexta-Feira",
                "voice": stored_voice,
                "system_commands_enabled": stored_sys,
                "configured": bool(stored_key)
            }
            
    # Fallback apenas para variáveis de ambiente locais se existirem
    env_key = (os.getenv("GEMINI_API_KEY") or os.getenv("OPENAI_API_KEY") or "").strip()
    env_model = os.getenv("DEFAULT_MODEL", "gemini-2.5-flash-lite")
    env_agent_name = os.getenv("AGENT_NAME", "Sexta-Feira")
    env_voice = os.getenv("DEFAULT_VOICE", "pt-BR-FranciscaNeural")
    masked_env = f"{env_key[:6]}...{env_key[-4:]}" if len(env_key) > 10 else ("Configurada" if env_key else "")
    return {
        "api_key": env_key,
        "masked_key": masked_env,
        "ai_model": env_model,
        "agent_name": env_agent_name,
        "voice": env_voice,
        "system_commands_enabled": False,
        "configured": bool(env_key)
    }

def db_get_system_commands_flag(user_email: str) -> bool:
    """Verifica de forma rápida se o usuário permitiu comandos de máquina/sistema operacional."""
    cfg = db_get_ai_config(user_email)
    return bool(cfg.get("system_commands_enabled", False))

def db_save_system_commands_flag(user_email: str, enabled: bool) -> bool:
    """Atualiza a flag de permissão de comandos de máquina do usuário."""
    clean_email = (user_email or "").strip().lower()
    if not clean_email:
        return False
    db_save_ai_config(user_email=clean_email, system_commands_enabled=enabled)
    return True


# =========================================================================
# CONFIGURAÇÕES DA CASA & CÔMODOS (SQLite)
# =========================================================================

DEFAULT_HOUSE_ROOMS = [
    {"id": 1, "name": "Sala de Estar", "topic": "saladeestar"},
    {"id": 2, "name": "Quarto Principal", "topic": "quartoprincipal"},
    {"id": 3, "name": "Cozinha", "topic": "cozinha"},
    {"id": 4, "name": "Escritório", "topic": "escritorio"}
]

def db_get_house_config(user_email: str) -> Dict[str, Any]:
    """Retorna as configurações de conexão MQTT e a lista de cômodos da casa do usuário."""
    clean_email = (user_email or "").strip().lower()
    if not clean_email:
        return {
            "broker": "test.mosquitto.org",
            "port": "8080",
            "topic_prefix": "pensador/casa",
            "rooms": DEFAULT_HOUSE_ROOMS
        }
        
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM user_house_configs WHERE user_email = ?", (clean_email,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        rooms_list = []
        try:
            rooms_list = json.loads(row["rooms_json"] or "[]")
        except Exception:
            rooms_list = []
        return {
            "broker": row["broker"] or "test.mosquitto.org",
            "port": str(row["port"] or "8080"),
            "topic_prefix": row["topic_prefix"] or "pensador/casa",
            "rooms": rooms_list if rooms_list else DEFAULT_HOUSE_ROOMS
        }
        
    return {
        "broker": "test.mosquitto.org",
        "port": "8080",
        "topic_prefix": "pensador/casa",
        "rooms": DEFAULT_HOUSE_ROOMS
    }

def db_save_house_config(
    user_email: str,
    broker: Optional[str] = "test.mosquitto.org",
    port: Optional[str] = "8080",
    topic_prefix: Optional[str] = "pensador/casa",
    rooms: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """Salva ou atualiza a configuração da casa (broker, porta e cômodos) no banco de dados SQLite."""
    clean_email = (user_email or "").strip().lower()
    if not clean_email:
        clean_email = "anonimo@smarthome.local"
        
    broker_clean = (broker or "test.mosquitto.org").strip()
    port_clean = str(port or "8080").strip()
    prefix_clean = (topic_prefix or "pensador/casa").strip()
    rooms_list = rooms if isinstance(rooms, list) else DEFAULT_HOUSE_ROOMS
    rooms_json_str = json.dumps(rooms_list, ensure_ascii=False)
    now_iso = datetime.now(timezone.utc).isoformat()
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO user_house_configs (user_email, broker, port, topic_prefix, rooms_json, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_email) DO UPDATE SET
            broker = excluded.broker,
            port = excluded.port,
            topic_prefix = excluded.topic_prefix,
            rooms_json = excluded.rooms_json,
            updated_at = excluded.updated_at
    """, (clean_email, broker_clean, port_clean, prefix_clean, rooms_json_str, now_iso))
    conn.commit()
    conn.close()
    
    system_logger.info(f"[HouseConfig] Configuração da casa salva no banco para '{clean_email}' com {len(rooms_list)} cômodos.")
    return {
        "broker": broker_clean,
        "port": port_clean,
        "topic_prefix": prefix_clean,
        "rooms": rooms_list
    }


# =========================================================================
# HISTÓRICO E MEMÓRIA DE MENSAGENS (SQLite)
# =========================================================================

def save_chat_message(user_email: str, user_message: str, agent_response: str) -> Dict[str, Any]:
    """
    Salva uma interação (pergunta do usuário e resposta gerada pelo agente)
    no histórico de mensagens vinculado ao e-mail do usuário.
    """
    clean_email = (user_email or "").strip().lower()
    if not clean_email:
        clean_email = "anonimo@smarthome.local"
        
    created_at = datetime.now(timezone.utc).isoformat()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO chat_history (user_email, user_message, agent_response, created_at)
        VALUES (?, ?, ?, ?)
    """, (clean_email, user_message.strip(), agent_response.strip(), created_at))
    conn.commit()
    inserted_id = cursor.lastrowid
    conn.close()
    
    system_logger.info(f"Interação salva no histórico (ID {inserted_id}) para: {clean_email}")
    return {
        "id": inserted_id,
        "user_email": clean_email,
        "user_message": user_message,
        "agent_response": agent_response,
        "created_at": created_at
    }

def get_chat_history(user_email: str, limit: int = 5) -> List[Dict[str, Any]]:
    """
    Recupera as últimas `limit` mensagens/interações do usuário em ordem cronológica
    (da mais antiga para a mais recente) para fornecer contexto conversacional ao agente.
    """
    clean_email = (user_email or "").strip().lower()
    if not clean_email:
        return []
        
    conn = get_db_connection()
    cursor = conn.cursor()
    # Busca as últimas 'limit' mensagens em ordem decrescente
    cursor.execute("""
        SELECT id, user_email, user_message, agent_response, created_at
        FROM chat_history
        WHERE user_email = ?
        ORDER BY id DESC
        LIMIT ?
    """, (clean_email, limit))
    rows = cursor.fetchall()
    conn.close()
    
    # Inverte para que a lista fique em ordem cronológica correta (passado -> presente)
    history = [dict(r) for r in reversed(rows)]
    return history

def clear_chat_history(user_email: str) -> bool:
    """Limpa todo o histórico de mensagens de um usuário específico."""
    clean_email = (user_email or "").strip().lower()
    if not clean_email:
        return False
        
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM chat_history WHERE user_email = ?", (clean_email,))
    conn.commit()
    deleted_count = cursor.rowcount
    conn.close()
    system_logger.info(f"Histórico de chat limpo para {clean_email} ({deleted_count} registros removidos).")
    return True

# =========================================================================
# OPERAÇÕES DE CONTATOS NO BANCO SQLITE (CACHE / PERSISTÊNCIA)
# =========================================================================

def db_upsert_contact(user_email: str, uid: str, href: str, name: str, phones: str = "", emails: str = "", notes: str = "") -> None:
    """Insere ou atualiza um contato no cache local do banco SQLite."""
    clean_email = (user_email or "").strip().lower()
    updated_at = datetime.now(timezone.utc).isoformat()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO google_contacts (user_email, uid, href, name, phones, emails, notes, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_email, uid) DO UPDATE SET
            href = excluded.href,
            name = excluded.name,
            phones = excluded.phones,
            emails = excluded.emails,
            notes = excluded.notes,
            updated_at = excluded.updated_at
    """, (clean_email, uid, href, name, phones, emails, notes, updated_at))
    conn.commit()
    conn.close()

def db_get_contacts(user_email: str, limit: int = 50) -> List[Dict[str, Any]]:
    """Retorna os contatos cacheados do usuário ordenados por nome."""
    clean_email = (user_email or "").strip().lower()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT uid, href, name, phones, emails, notes, updated_at
        FROM google_contacts
        WHERE user_email = ?
        ORDER BY name ASC
        LIMIT ?
    """, (clean_email, limit))
    rows = cursor.fetchall()
    conn.close()
    
    contacts = []
    for r in rows:
        c = dict(r)
        c["phones"] = [p.strip() for p in c["phones"].split(";") if p.strip()] if c["phones"] else []
        c["emails"] = [e.strip() for e in c["emails"].split(";") if e.strip()] if c["emails"] else []
        contacts.append(c)
    return contacts

def db_search_contacts(user_email: str, term: str) -> List[Dict[str, Any]]:
    """Busca contatos locais por nome, telefone ou e-mail."""
    clean_email = (user_email or "").strip().lower()
    term_pattern = f"%{term.strip()}%"
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT uid, href, name, phones, emails, notes, updated_at
        FROM google_contacts
        WHERE user_email = ? AND (name LIKE ? OR phones LIKE ? OR emails LIKE ? OR notes LIKE ?)
        ORDER BY name ASC
    """, (clean_email, term_pattern, term_pattern, term_pattern, term_pattern))
    rows = cursor.fetchall()
    conn.close()
    
    contacts = []
    for r in rows:
        c = dict(r)
        c["phones"] = [p.strip() for p in c["phones"].split(";") if p.strip()] if c["phones"] else []
        c["emails"] = [e.strip() for e in c["emails"].split(";") if e.strip()] if c["emails"] else []
        contacts.append(c)
    return contacts

def db_delete_contact(user_email: str, uid_or_href: str) -> bool:
    """Remove um contato do cache local pelo UID ou href."""
    clean_email = (user_email or "").strip().lower()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        DELETE FROM google_contacts 
        WHERE user_email = ? AND (uid = ? OR href = ?)
    """, (clean_email, uid_or_href, uid_or_href))
    conn.commit()
    deleted = cursor.rowcount > 0
    conn.close()
    return deleted

def db_get_contacts_count(user_email: str) -> int:
    """Retorna o número total de contatos cacheados."""
    clean_email = (user_email or "").strip().lower()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM google_contacts WHERE user_email = ?", (clean_email,))
    count = cursor.fetchone()[0]
    conn.close()
    return count

# =========================================================================
# OPERAÇÕES DE TAREFAS E LEMBRETES (USER_TASKS)
# =========================================================================

def db_create_task(
    user_email: str,
    title: str,
    description: str = "",
    due_date: str = "",
    due_time: str = "",
    priority: str = "media",
    calendar_event_uid: str = ""
) -> Dict[str, Any]:
    """Cria e salva uma nova tarefa no banco de dados SQLite."""
    clean_email = (user_email or "").strip().lower()
    created_at = datetime.now(timezone.utc).isoformat()
    clean_priority = (priority or "media").lower()
    if clean_priority not in ("alta", "media", "baixa"):
        clean_priority = "media"
        
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO user_tasks (
            user_email, title, description, due_date, due_time, 
            priority, status, calendar_event_uid, created_at, completed_at
        ) VALUES (?, ?, ?, ?, ?, ?, 'pendente', ?, ?, '')
    """, (clean_email, title.strip(), description.strip(), due_date.strip(), due_time.strip(), clean_priority, calendar_event_uid.strip(), created_at))
    task_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    return {
        "id": task_id,
        "user_email": clean_email,
        "title": title.strip(),
        "description": description.strip(),
        "due_date": due_date.strip(),
        "due_time": due_time.strip(),
        "priority": clean_priority,
        "status": "pendente",
        "calendar_event_uid": calendar_event_uid.strip(),
        "created_at": created_at,
        "completed_at": ""
    }

def db_get_tasks(
    user_email: str,
    status: str = "pendente",
    filter_date: str = "todas",
    limit: int = 50
) -> List[Dict[str, Any]]:
    """Recupera a lista de tarefas do usuário com filtros opcionais."""
    clean_email = (user_email or "").strip().lower()
    conn = get_db_connection()
    cursor = conn.cursor()
    
    query = "SELECT * FROM user_tasks WHERE user_email = ?"
    params: List[Any] = [clean_email]
    
    if status and status != "todas":
        query += " AND status = ?"
        params.append(status.lower())
        
    if filter_date == "hoje":
        today_str = datetime.now().strftime("%Y-%m-%d")
        query += " AND (due_date = ? OR due_date = '')"
        params.append(today_str)
    elif filter_date and filter_date != "todas":
        query += " AND due_date = ?"
        params.append(filter_date)
        
    query += " ORDER BY CASE priority WHEN 'alta' THEN 1 WHEN 'media' THEN 2 WHEN 'baixa' THEN 3 ELSE 4 END, due_date ASC, id DESC LIMIT ?"
    params.append(limit)
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def db_complete_task(user_email: str, task_id_or_title: str) -> Optional[Dict[str, Any]]:
    """Marca uma tarefa como concluída buscando por ID ou título."""
    clean_email = (user_email or "").strip().lower()
    now_iso = datetime.now(timezone.utc).isoformat()
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Tenta por ID numérico
    if str(task_id_or_title).strip().isdigit():
        cursor.execute("""
            UPDATE user_tasks 
            SET status = 'concluida', completed_at = ? 
            WHERE user_email = ? AND id = ?
        """, (now_iso, clean_email, int(task_id_or_title)))
    else:
        pattern = f"%{task_id_or_title.strip()}%"
        cursor.execute("""
            UPDATE user_tasks 
            SET status = 'concluida', completed_at = ? 
            WHERE user_email = ? AND title LIKE ? AND status = 'pendente'
        """, (now_iso, clean_email, pattern))
        
    if cursor.rowcount > 0:
        cursor.execute("""
            SELECT * FROM user_tasks WHERE user_email = ? AND (id = ? OR title LIKE ?) ORDER BY id DESC LIMIT 1
        """, (clean_email, task_id_or_title if str(task_id_or_title).isdigit() else -1, f"%{task_id_or_title}%"))
        row = cursor.fetchone()
        conn.commit()
        conn.close()
        return dict(row) if row else None
        
    conn.close()
    return None

def db_delete_task(user_email: str, task_id_or_title: str) -> Optional[Dict[str, Any]]:
    """Exclui uma tarefa do banco pelo ID ou título e retorna os dados excluídos."""
    clean_email = (user_email or "").strip().lower()
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Localiza a tarefa antes de excluir para retornar o calendar_event_uid se houver
    if str(task_id_or_title).strip().isdigit():
        cursor.execute("SELECT * FROM user_tasks WHERE user_email = ? AND id = ?", (clean_email, int(task_id_or_title)))
    else:
        cursor.execute("SELECT * FROM user_tasks WHERE user_email = ? AND title LIKE ? LIMIT 1", (clean_email, f"%{task_id_or_title.strip()}%"))
        
    row = cursor.fetchone()
    if row:
        task_data = dict(row)
        cursor.execute("DELETE FROM user_tasks WHERE id = ?", (task_data["id"],))
        conn.commit()
        conn.close()
        return task_data
        
    conn.close()
    return None

def db_search_tasks(user_email: str, term: str) -> List[Dict[str, Any]]:
    """Busca tarefas no banco por termo ou palavra-chave."""
    clean_email = (user_email or "").strip().lower()
    pattern = f"%{term.strip()}%"
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM user_tasks 
        WHERE user_email = ? AND (title LIKE ? OR description LIKE ?)
        ORDER BY status ASC, due_date ASC, id DESC
    """, (clean_email, pattern, pattern))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def db_get_tasks_count(user_email: str, status: str = "pendente") -> int:
    """Retorna o número de tarefas no banco."""
    clean_email = (user_email or "").strip().lower()
    conn = get_db_connection()
    cursor = conn.cursor()
    if status == "todas":
        cursor.execute("SELECT COUNT(*) FROM user_tasks WHERE user_email = ?", (clean_email,))
    else:
        cursor.execute("SELECT COUNT(*) FROM user_tasks WHERE user_email = ? AND status = ?", (clean_email, status.lower()))
    count = cursor.fetchone()[0]
    conn.close()
    return count

# =========================================================================
# OPERAÇÕES DE NOTAS E LISTAS DE COMPRAS (GOOGLE KEEP / USER_NOTES)
# =========================================================================

def _get_note_items(cursor: sqlite3.Cursor, note_id: int) -> List[Dict[str, Any]]:
    """Busca os itens de checklist de uma nota."""
    cursor.execute("""
        SELECT id, item_text, is_completed, created_at 
        FROM note_checklist_items 
        WHERE note_id = ? 
        ORDER BY is_completed ASC, id ASC
    """, (note_id,))
    rows = cursor.fetchall()
    return [dict(r) for r in rows]

def db_create_note(
    user_email: str,
    title: str,
    content: str = "",
    note_type: str = "texto",
    color: str = "padrao",
    is_pinned: bool = False,
    items: Optional[List[str]] = None
) -> Dict[str, Any]:
    """Cria uma nova nota de texto ou lista de compras com itens no SQLite."""
    clean_email = (user_email or "").strip().lower()
    now_iso = datetime.now(timezone.utc).isoformat()
    clean_type = "lista" if note_type in ("lista", "checklist", "compras") else "texto"
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO user_notes (user_email, title, content, note_type, color, is_pinned, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (clean_email, title.strip(), content.strip(), clean_type, color.strip(), 1 if is_pinned else 0, now_iso, now_iso))
    note_id = cursor.lastrowid
    
    checklist_items = []
    if items:
        for it in items:
            it_clean = it.strip()
            if it_clean:
                cursor.execute("""
                    INSERT INTO note_checklist_items (note_id, item_text, is_completed, created_at)
                    VALUES (?, ?, 0, ?)
                """, (note_id, it_clean, now_iso))
                checklist_items.append({"id": cursor.lastrowid, "item_text": it_clean, "is_completed": 0})
                
    conn.commit()
    conn.close()
    
    return {
        "id": note_id,
        "user_email": clean_email,
        "title": title.strip(),
        "content": content.strip(),
        "note_type": clean_type,
        "color": color.strip(),
        "is_pinned": bool(is_pinned),
        "items": checklist_items,
        "created_at": now_iso,
        "updated_at": now_iso
    }

def db_get_notes(user_email: str, note_type: str = "todas", limit: int = 50) -> List[Dict[str, Any]]:
    """Retorna as notas e listas de compras do usuário."""
    clean_email = (user_email or "").strip().lower()
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if note_type and note_type != "todas":
        clean_type = "lista" if note_type in ("lista", "compras") else "texto"
        cursor.execute("""
            SELECT * FROM user_notes 
            WHERE user_email = ? AND note_type = ?
            ORDER BY is_pinned DESC, updated_at DESC, id DESC LIMIT ?
        """, (clean_email, clean_type, limit))
    else:
        cursor.execute("""
            SELECT * FROM user_notes 
            WHERE user_email = ?
            ORDER BY is_pinned DESC, updated_at DESC, id DESC LIMIT ?
        """, (clean_email, limit))
        
    rows = cursor.fetchall()
    notes = []
    for r in rows:
        n = dict(r)
        if n["note_type"] == "lista":
            n["items"] = _get_note_items(cursor, n["id"])
        else:
            n["items"] = []
        notes.append(n)
        
    conn.close()
    return notes

def db_get_note_by_id_or_title(user_email: str, note_id_or_title: str) -> Optional[Dict[str, Any]]:
    """Busca uma nota específica pelo ID ou título."""
    clean_email = (user_email or "").strip().lower()
    conn = get_db_connection()
    cursor = conn.cursor()
    
    if str(note_id_or_title).strip().isdigit():
        cursor.execute("SELECT * FROM user_notes WHERE user_email = ? AND id = ?", (clean_email, int(note_id_or_title)))
    else:
        cursor.execute("SELECT * FROM user_notes WHERE user_email = ? AND title LIKE ? ORDER BY id DESC LIMIT 1", (clean_email, f"%{note_id_or_title.strip()}%"))
        
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None
        
    n = dict(row)
    if n["note_type"] == "lista":
        n["items"] = _get_note_items(cursor, n["id"])
    else:
        n["items"] = []
        
    conn.close()
    return n

def db_add_items_to_note(user_email: str, note_id_or_title: str, items: List[str]) -> Optional[Dict[str, Any]]:
    """Adiciona novos itens a uma lista de compras ou notas existente."""
    clean_email = (user_email or "").strip().lower()
    now_iso = datetime.now(timezone.utc).isoformat()
    note = db_get_note_by_id_or_title(clean_email, note_id_or_title)
    if not note:
        return None
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Atualiza tipo da nota para lista caso ainda não seja
    cursor.execute("UPDATE user_notes SET note_type = 'lista', updated_at = ? WHERE id = ?", (now_iso, note["id"]))
    
    for it in items:
        it_clean = it.strip()
        if it_clean:
            cursor.execute("""
                INSERT INTO note_checklist_items (note_id, item_text, is_completed, created_at)
                VALUES (?, ?, 0, ?)
            """, (note["id"], it_clean, now_iso))
            
    conn.commit()
    note_updated = db_get_note_by_id_or_title(clean_email, str(note["id"]))
    conn.close()
    return note_updated

def db_toggle_note_item(user_email: str, note_id_or_title: str, item_text: str, is_completed: bool = True) -> Optional[Dict[str, Any]]:
    """Marca ou desmarca um item da lista de compras como concluído/comprado."""
    clean_email = (user_email or "").strip().lower()
    now_iso = datetime.now(timezone.utc).isoformat()
    note = db_get_note_by_id_or_title(clean_email, note_id_or_title)
    if not note:
        return None
        
    conn = get_db_connection()
    cursor = conn.cursor()
    
    pattern = f"%{item_text.strip()}%"
    cursor.execute("""
        UPDATE note_checklist_items 
        SET is_completed = ? 
        WHERE note_id = ? AND item_text LIKE ?
    """, (1 if is_completed else 0, note["id"], pattern))
    
    if cursor.rowcount > 0:
        cursor.execute("UPDATE user_notes SET updated_at = ? WHERE id = ?", (now_iso, note["id"]))
        conn.commit()
        note_updated = db_get_note_by_id_or_title(clean_email, str(note["id"]))
        conn.close()
        return note_updated
        
    conn.close()
    return None

def db_delete_note(user_email: str, note_id_or_title: str) -> Optional[Dict[str, Any]]:
    """Exclui uma nota ou lista de compras e seus itens."""
    clean_email = (user_email or "").strip().lower()
    note = db_get_note_by_id_or_title(clean_email, note_id_or_title)
    if not note:
        return None
        
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM note_checklist_items WHERE note_id = ?", (note["id"],))
    cursor.execute("DELETE FROM user_notes WHERE id = ?", (note["id"],))
    conn.commit()
    conn.close()
    return note

def db_search_notes(user_email: str, term: str) -> List[Dict[str, Any]]:
    """Busca notas por texto no título, conteúdo ou itens de checklist."""
    clean_email = (user_email or "").strip().lower()
    pattern = f"%{term.strip()}%"
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT DISTINCT n.* FROM user_notes n
        LEFT JOIN note_checklist_items i ON n.id = i.note_id
        WHERE n.user_email = ? AND (n.title LIKE ? OR n.content LIKE ? OR i.item_text LIKE ?)
        ORDER BY n.is_pinned DESC, n.updated_at DESC, n.id DESC
    """, (clean_email, pattern, pattern, pattern))
    rows = cursor.fetchall()
    
    notes = []
    for r in rows:
        n = dict(r)
        if n["note_type"] == "lista":
            n["items"] = _get_note_items(cursor, n["id"])
        else:
            n["items"] = []
        notes.append(n)
        
    conn.close()
    return notes

def db_get_notes_count(user_email: str, note_type: str = "todas") -> int:
    """Retorna a contagem de notas salvas."""
    clean_email = (user_email or "").strip().lower()
    conn = get_db_connection()
    cursor = conn.cursor()
    if note_type == "todas":
        cursor.execute("SELECT COUNT(*) FROM user_notes WHERE user_email = ?", (clean_email,))
    else:
        clean_type = "lista" if note_type in ("lista", "compras") else "texto"
        cursor.execute("SELECT COUNT(*) FROM user_notes WHERE user_email = ? AND note_type = ?", (clean_email, clean_type))
    count = cursor.fetchone()[0]
    conn.close()
    return count


# =========================================================================
# MOTOR DE AUTOMAÇÕES E AGENDAMENTOS EM SEGUNDO PLANO (SQLite)
# =========================================================================

def db_create_automation(
    user_email: str,
    name: str,
    automation_type: str,
    trigger_type: str,
    trigger_value: str,
    action_type: str,
    action_payload: Optional[Dict[str, Any]] = None,
    is_enabled: bool = True
) -> Dict[str, Any]:
    """Cria uma nova regra de automação no SQLite para o usuário."""
    clean_email = (user_email or "").strip().lower()
    clean_name = (name or "Automação").strip()
    payload_str = json.dumps(action_payload or {}, ensure_ascii=False)
    now = datetime.now(timezone.utc).isoformat()
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO user_automations (
            user_email, name, automation_type, trigger_type, trigger_value,
            action_type, action_payload, is_enabled, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        clean_email, clean_name, automation_type, trigger_type, str(trigger_value).strip(),
        action_type, payload_str, 1 if is_enabled else 0, now, now
    ))
    auto_id = cursor.lastrowid
    conn.commit()
    conn.close()
    system_logger.info(f"Automação '{clean_name}' (ID {auto_id}) criada para {clean_email}")
    return db_get_automation_by_id(clean_email, auto_id)

def db_get_automations(user_email: str) -> List[Dict[str, Any]]:
    """Retorna todas as automações cadastradas pelo usuário."""
    clean_email = (user_email or "").strip().lower()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM user_automations 
        WHERE user_email = ? 
        ORDER BY is_enabled DESC, updated_at DESC, id DESC
    """, (clean_email,))
    rows = cursor.fetchall()
    conn.close()
    
    automations = []
    for r in rows:
        item = dict(r)
        item["is_enabled"] = bool(item["is_enabled"])
        try:
            item["action_payload"] = json.loads(item["action_payload"]) if item.get("action_payload") else {}
        except Exception:
            item["action_payload"] = {}
        automations.append(item)
    return automations

def db_get_automation_by_id(user_email: str, auto_id: int) -> Optional[Dict[str, Any]]:
    """Retorna uma automação específica pelo ID."""
    clean_email = (user_email or "").strip().lower()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM user_automations WHERE user_email = ? AND id = ?", (clean_email, auto_id))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return None
    item = dict(row)
    item["is_enabled"] = bool(item["is_enabled"])
    try:
        item["action_payload"] = json.loads(item["action_payload"]) if item.get("action_payload") else {}
    except Exception:
        item["action_payload"] = {}
    return item

def db_update_automation(user_email: str, auto_id: int, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Atualiza os parâmetros de uma automação."""
    clean_email = (user_email or "").strip().lower()
    current = db_get_automation_by_id(clean_email, auto_id)
    if not current:
        return None
        
    name = data.get("name", current["name"])
    automation_type = data.get("automation_type", current["automation_type"])
    trigger_type = data.get("trigger_type", current["trigger_type"])
    trigger_value = data.get("trigger_value", current["trigger_value"])
    action_type = data.get("action_type", current["action_type"])
    
    payload = data.get("action_payload", current["action_payload"])
    payload_str = json.dumps(payload if isinstance(payload, dict) else {}, ensure_ascii=False)
    
    is_enabled = data.get("is_enabled", current["is_enabled"])
    now = datetime.now(timezone.utc).isoformat()
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE user_automations SET
            name = ?, automation_type = ?, trigger_type = ?, trigger_value = ?,
            action_type = ?, action_payload = ?, is_enabled = ?, updated_at = ?
        WHERE user_email = ? AND id = ?
    """, (
        name, automation_type, trigger_type, str(trigger_value).strip(),
        action_type, payload_str, 1 if is_enabled else 0, now,
        clean_email, auto_id
    ))
    conn.commit()
    conn.close()
    return db_get_automation_by_id(clean_email, auto_id)

def db_delete_automation(user_email: str, auto_id: int) -> bool:
    """Exclui uma automação e seus registros de deduplicação."""
    clean_email = (user_email or "").strip().lower()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM user_automations WHERE user_email = ? AND id = ?", (clean_email, auto_id))
    deleted = cursor.rowcount > 0
    if deleted:
        cursor.execute("DELETE FROM automation_notified_events WHERE automation_id = ?", (auto_id,))
    conn.commit()
    conn.close()
    return deleted

def db_toggle_automation(user_email: str, auto_id: int) -> Optional[Dict[str, Any]]:
    """Alterna o status ativado/desativado de uma automação."""
    current = db_get_automation_by_id(user_email, auto_id)
    if not current:
        return None
    new_state = not current["is_enabled"]
    return db_update_automation(user_email, auto_id, {"is_enabled": new_state})

def db_get_all_active_automations() -> List[Dict[str, Any]]:
    """Retorna todas as automações ativas de todos os usuários para o AutomationEngine."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT a.*, p.telegram_bot_token, p.telegram_chat_id, p.telegram_enabled
        FROM user_automations a
        LEFT JOIN user_profiles p ON LOWER(a.user_email) = LOWER(p.user_email)
        WHERE a.is_enabled = 1
    """)
    rows = cursor.fetchall()
    conn.close()
    
    active = []
    for r in rows:
        item = dict(r)
        item["is_enabled"] = True
        try:
            item["action_payload"] = json.loads(item["action_payload"]) if item.get("action_payload") else {}
        except Exception:
            item["action_payload"] = {}
        active.append(item)
    return active

def db_record_automation_run(auto_id: int, status: str = "success", result: str = ""):
    """Registra o timestamp e resultado da execução da automação."""
    now = datetime.now(timezone.utc).isoformat()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE user_automations SET
            last_run_at = ?, last_status = ?, last_result = ?, updated_at = ?
        WHERE id = ?
    """, (now, status, (result or "")[:500], now, auto_id))
    conn.commit()
    conn.close()

def db_is_event_already_notified(automation_id: int, event_key: str) -> bool:
    """Verifica se determinado evento já foi notificado por esta automação."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id FROM automation_notified_events 
        WHERE automation_id = ? AND event_key = ?
    """, (automation_id, event_key))
    row = cursor.fetchone()
    conn.close()
    return bool(row)

def db_mark_event_notified(automation_id: int, user_email: str, event_key: str):
    """Marca um evento como já notificado para evitar duplicações."""
    now = datetime.now(timezone.utc).isoformat()
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT OR IGNORE INTO automation_notified_events (
                automation_id, user_email, event_key, notified_at
            ) VALUES (?, ?, ?, ?)
        """, (automation_id, (user_email or "").lower().strip(), event_key, now))
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()

def db_get_automations_count(user_email: str) -> Dict[str, int]:
    """Retorna contadores de automações do usuário."""
    clean_email = (user_email or "").strip().lower()
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM user_automations WHERE user_email = ?", (clean_email,))
    total = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM user_automations WHERE user_email = ? AND is_enabled = 1", (clean_email,))
    active = cursor.fetchone()[0]
    conn.close()
    return {"total": total, "active": active}

# =========================================================================
# MEMÓRIA DE LONGO PRAZO & APRENDIZADO AUTÔNOMO DO AGENTE
# =========================================================================

def db_save_agent_memory(
    user_email: str,
    fact: str,
    category: str = "geral",
    importance: int = 3,
    context: str = ""
) -> Dict[str, Any]:
    """
    Grava ou atualiza uma memória/fato de longo prazo aprendido pelo agente sobre o usuário.
    Evita duplicações exatas e atualiza timestamp de atualização.
    """
    clean_email = (user_email or "").strip().lower()
    clean_fact = (fact or "").strip()
    clean_category = (category or "geral").strip().lower()
    importance_val = max(1, min(5, int(importance or 3)))
    clean_context = (context or "").strip()
    now = datetime.now(timezone.utc).isoformat()

    if not clean_email or not clean_fact:
        return {"status": "error", "message": "E-mail do usuário e fato memorizado são obrigatórios."}

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        # Verifica se já existe um fato muito similar
        cursor.execute("""
            SELECT id, fact, category, importance, context FROM agent_long_term_memories
            WHERE user_email = ? AND LOWER(TRIM(fact)) = LOWER(TRIM(?))
        """, (clean_email, clean_fact))
        existing = cursor.fetchone()

        if existing:
            mem_id = existing["id"]
            new_importance = max(existing["importance"], importance_val)
            new_context = clean_context or existing["context"]
            cursor.execute("""
                UPDATE agent_long_term_memories
                SET category = ?, importance = ?, context = ?, updated_at = ?, last_accessed_at = ?
                WHERE id = ?
            """, (clean_category, new_importance, new_context, now, now, mem_id))
            conn.commit()
            return {
                "status": "updated",
                "id": mem_id,
                "fact": clean_fact,
                "category": clean_category,
                "importance": new_importance,
                "context": new_context,
                "updated_at": now
            }
        else:
            cursor.execute("""
                INSERT INTO agent_long_term_memories (
                    user_email, fact, category, importance, context, created_at, updated_at, last_accessed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (clean_email, clean_fact, clean_category, importance_val, clean_context, now, now, now))
            conn.commit()
            new_id = cursor.lastrowid
            return {
                "status": "created",
                "id": new_id,
                "fact": clean_fact,
                "category": clean_category,
                "importance": importance_val,
                "context": clean_context,
                "created_at": now
            }
    except Exception as e:
        system_logger.error(f"[Database] Erro ao salvar memória de longo prazo: {e}")
        return {"status": "error", "message": str(e)}
    finally:
        conn.close()

def db_search_agent_memories(
    user_email: str,
    query: str = "",
    category: str = "",
    limit: int = 20
) -> List[Dict[str, Any]]:
    """
    Pesquisa memórias de longo prazo do usuário por palavra-chave ou categoria.
    """
    clean_email = (user_email or "").strip().lower()
    clean_query = (query or "").strip().lower()
    clean_cat = (category or "").strip().lower()

    if not clean_email:
        return []

    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        sql = "SELECT * FROM agent_long_term_memories WHERE user_email = ?"
        params = [clean_email]

        if clean_cat:
            sql += " AND category = ?"
            params.append(clean_cat)

        if clean_query:
            sql += " AND (LOWER(fact) LIKE ? OR LOWER(context) LIKE ?)"
            term = f"%{clean_query}%"
            params.extend([term, term])

        sql += " ORDER BY importance DESC, updated_at DESC LIMIT ?"
        params.append(limit)

        cursor.execute(sql, params)
        rows = cursor.fetchall()
        results = [dict(r) for r in rows]

        # Atualiza timestamp de último acesso
        if results:
            now = datetime.now(timezone.utc).isoformat()
            ids = [r["id"] for r in results]
            placeholders = ",".join(["?"] * len(ids))
            cursor.execute(f"UPDATE agent_long_term_memories SET last_accessed_at = ? WHERE id IN ({placeholders})", [now] + ids)
            conn.commit()

        return results
    except Exception as e:
        system_logger.error(f"[Database] Erro ao buscar memórias: {e}")
        return []
    finally:
        conn.close()

def db_get_all_agent_memories(user_email: str, category: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
    """Retorna todas as memórias gravadas para o usuário (com filtro opcional por categoria)."""
    return db_search_agent_memories(user_email=user_email, query="", category=category or "", limit=limit)

def db_delete_agent_memory(user_email: str, memory_id: int) -> bool:
    """Exclui uma memória específica do agente para o usuário."""
    clean_email = (user_email or "").strip().lower()
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM agent_long_term_memories WHERE user_email = ? AND id = ?", (clean_email, memory_id))
        conn.commit()
        return cursor.rowcount > 0
    except Exception as e:
        system_logger.error(f"[Database] Erro ao excluir memória: {e}")
        return False
    finally:
        conn.close()

def db_get_recent_important_memories_summary(user_email: str, limit: int = 10) -> str:
    """
    Retorna um resumo formatado em texto das principais memórias ativas de longo prazo
    para ser injetado no prompt de contexto do agente.
    """
    memories = db_search_agent_memories(user_email=user_email, limit=limit)
    if not memories:
        return ""
    
    lines = []
    for m in memories:
        cat_badge = f"[{m.get('category', 'geral')}]"
        fact_text = m.get("fact", "").strip()
        lines.append(f"- {cat_badge} {fact_text}")
    
    return "\n".join(lines)

# Inicializa o banco automaticamente ao carregar o módulo
init_db()

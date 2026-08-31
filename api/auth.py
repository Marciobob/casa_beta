import os
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any

try:
    import jwt
except ImportError:
    jwt = None

try:
    from api.database import get_db_connection
    from api.logger import auth_logger
except ImportError:
    from database import get_db_connection
    from logger import auth_logger

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "smart_home_secret_key_2026_jwt_token_secure_98412")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 7

def hash_password(password: str) -> str:
    """Gera um hash seguro SHA-256 com salt individual de 16 bytes."""
    salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        100000
    )
    return f"{salt}${key.hex()}"

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica se a senha em texto puro corresponde ao hash armazenado."""
    try:
        salt, key_hex = hashed_password.split("$")
        key = hashlib.pbkdf2_hmac(
            'sha256',
            plain_password.encode('utf-8'),
            salt.encode('utf-8'),
            100000
        )
        return secrets.compare_digest(key.hex(), key_hex)
    except Exception as e:
        auth_logger.error(f"Erro ao verificar senha: {e}")
        return False

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Gera um JWT Token assinado contendo os dados do usuário."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(days=ACCESS_TOKEN_EXPIRE_DAYS))
    to_encode.update({"exp": expire})
    
    if jwt is not None:
        encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
        return encoded_jwt
    else:
        # Fallback simples caso pyjwt não esteja instalado
        raw = f"{to_encode.get('sub')}:{secrets.token_hex(24)}"
        return raw

def decode_access_token(token: str) -> Optional[dict]:
    """Decodifica e valida o JWT Token."""
    if not token:
        return None
    try:
        if jwt is not None:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            return payload
        else:
            return {"sub": token.split(":")[0]}
    except Exception as e:
        auth_logger.warning(f"Tentativa com token JWT inválido ou expirado: {e}")
        return None

def get_user_by_email(email: str) -> Optional[Dict[str, Any]]:
    """Busca um usuário no banco SQLite pelo e-mail."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email = ?", (email.strip().lower(),))
    row = cursor.fetchone()
    conn.close()
    if row:
        return dict(row)
    return None

def register_user(name: str, phone: str, email: str, password: str) -> Dict[str, Any]:
    """Cadastra um novo usuário no banco de dados SQLite."""
    clean_email = email.strip().lower()
    clean_name = name.strip()
    clean_phone = phone.strip()
    
    auth_logger.info(f"Tentativa de cadastro para o e-mail: {clean_email}")
    
    if not clean_email or not password:
        auth_logger.warning("Tentativa de cadastro com campos obrigatórios vazios.")
        raise ValueError("E-mail e senha são obrigatórios.")
        
    if get_user_by_email(clean_email):
        auth_logger.warning(f"Cadastro rejeitado: e-mail '{clean_email}' já está em uso.")
        raise ValueError("Este e-mail já está cadastrado no sistema.")
        
    hashed_pwd = hash_password(password)
    created_at = datetime.now(timezone.utc).isoformat()
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO users (name, phone, email, hashed_password, created_at) VALUES (?, ?, ?, ?, ?)",
        (clean_name, clean_phone, clean_email, hashed_pwd, created_at)
    )
    user_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    auth_logger.info(f"Usuário cadastrado com sucesso! ID: {user_id}, E-mail: {clean_email}")
    
    return {
        "id": user_id,
        "name": clean_name,
        "phone": clean_phone,
        "email": clean_email,
        "created_at": created_at
    }

def authenticate_user(email: str, password: str) -> Optional[Dict[str, Any]]:
    """Autentica o usuário e retorna seus dados se a senha for válida."""
    clean_email = email.strip().lower()
    auth_logger.info(f"Tentativa de login para o e-mail: {clean_email}")
    
    user = get_user_by_email(clean_email)
    if not user:
        auth_logger.warning(f"Falha de login: usuário '{clean_email}' não encontrado.")
        return None
        
    if not verify_password(password, user["hashed_password"]):
        auth_logger.warning(f"Falha de login: senha incorreta para '{clean_email}'.")
        return None
        
    auth_logger.info(f"Login bem-sucedido para o usuário: {clean_email} (ID: {user['id']})")
    return {
        "id": user["id"],
        "name": user["name"],
        "phone": user.get("phone", ""),
        "email": user["email"]
    }

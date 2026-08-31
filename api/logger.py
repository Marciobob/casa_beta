import logging
import os
from pathlib import Path

# Diretório base de logs
LOGS_DIR = Path(__file__).parent / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

def setup_file_logger(name: str, log_filename: str, level=logging.INFO) -> logging.Logger:
    """Configura e retorna um logger dedicado gravando em um arquivo específico."""
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Evita duplicação de handlers se já estiver configurado
    if not logger.handlers:
        file_path = LOGS_DIR / log_filename
        
        file_handler = logging.FileHandler(file_path, encoding="utf-8")
        file_handler.setLevel(level)
        
        formatter = logging.Formatter(
            "[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        
        # Também envia para o console padrão
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        
    return logger

# Loggers dedicados para cada funcionalidade do sistema
auth_logger = setup_file_logger("AUTH", "auth.log")
agent_logger = setup_file_logger("AGENT", "agent.log")
mqtt_logger = setup_file_logger("MQTT", "mqtt.log")
system_logger = setup_file_logger("SYSTEM", "system.log")
gmail_logger = setup_file_logger("GMAIL", "gmail.log")
calendar_logger = setup_file_logger("CALENDAR", "calendar.log")
contacts_logger = setup_file_logger("CONTACTS", "contacts.log")
tasks_logger = setup_file_logger("TASKS", "tasks.log")
keep_logger = setup_file_logger("KEEP", "keep.log")
vision_logger = setup_file_logger("VISION", "vision.log")

import os
import io
import time
import threading
from typing import Optional, Dict, Any, Tuple, List
import requests

try:
    from api.logger import system_logger
    from api.database import (
        db_get_telegram_config, 
        db_save_telegram_config, 
        db_get_all_active_telegram_bots,
        get_user_profile,
        db_get_ai_config,
        get_chat_history,
        save_chat_message
    )
    from api.tools.vision_tools import capture_camera_frame, analyze_image_with_vision
    from api.tools.mqtt_tools import controlar_luzes, relatorio_status_casa
except ImportError:
    from logger import system_logger
    from database import (
        db_get_telegram_config, 
        db_save_telegram_config, 
        db_get_all_active_telegram_bots,
        get_user_profile,
        db_get_ai_config,
        get_chat_history,
        save_chat_message
    )
    from tools.vision_tools import capture_camera_frame, analyze_image_with_vision
    from tools.mqtt_tools import controlar_luzes, relatorio_status_casa


# =========================================================================
# FUNÇÕES NATIVAS DA TELEGRAM BOT API (HTTP REST)
# =========================================================================

def get_telegram_bot_info(bot_token: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Testa o token do bot chamando getMe na API do Telegram."""
    clean_token = (bot_token or "").strip()
    if not clean_token:
        return None, "Token do bot do Telegram não fornecido."
        
    url = f"https://api.telegram.org/bot{clean_token}/getMe"
    try:
        resp = requests.get(url, timeout=10)
        data = resp.json()
        if resp.status_code == 200 and data.get("ok"):
            return data.get("result"), None
        err = data.get("description", "Token inválido ou rejeitado pelo Telegram.")
        return None, err
    except Exception as e:
        return None, f"Erro de conexão com Telegram: {e}"


def send_telegram_message(bot_token: str, chat_id: str, text: str, parse_mode: Optional[str] = None) -> Tuple[bool, str]:
    """Envia uma mensagem de texto para um chat específico via Telegram Bot API."""
    clean_token = (bot_token or "").strip()
    clean_chat_id = str(chat_id or "").strip()
    if not clean_token or not clean_chat_id:
        return False, "Token do bot ou Chat ID não configurados."
        
    url = f"https://api.telegram.org/bot{clean_token}/sendMessage"
    payload = {
        "chat_id": clean_chat_id,
        "text": text
    }
    if parse_mode:
        payload["parse_mode"] = parse_mode
        
    try:
        resp = requests.post(url, json=payload, timeout=10)
        data = resp.json()
        if resp.status_code == 200 and data.get("ok"):
            return True, "Mensagem enviada com sucesso."
        err = data.get("description", f"Falha HTTP {resp.status_code}")
        return False, err
    except Exception as e:
        return False, f"Erro ao enviar mensagem Telegram: {e}"


def send_telegram_photo(bot_token: str, chat_id: str, photo_bytes: bytes, caption: str = "") -> Tuple[bool, str]:
    """Envia uma foto (JPEG) capturada das câmeras diretamente para o chat do Telegram."""
    clean_token = (bot_token or "").strip()
    clean_chat_id = str(chat_id or "").strip()
    if not clean_token or not clean_chat_id:
        return False, "Token do bot ou Chat ID não configurados."
        
    url = f"https://api.telegram.org/bot{clean_token}/sendPhoto"
    data = {"chat_id": clean_chat_id}
    if caption:
        data["caption"] = caption[:1024]
        
    files = {"photo": ("camera_snapshot.jpg", photo_bytes, "image/jpeg")}
    try:
        resp = requests.post(url, data=data, files=files, timeout=15)
        res_json = resp.json()
        if resp.status_code == 200 and res_json.get("ok"):
            return True, "Foto enviada com sucesso."
        err = res_json.get("description", f"Falha HTTP {resp.status_code}")
        return False, err
    except Exception as e:
        return False, f"Erro ao enviar foto para Telegram: {e}"


def send_telegram_chat_action(bot_token: str, chat_id: str, action: str = "typing"):
    """Envia ação de chat (ex: 'typing', 'upload_photo') para feedback visual no aplicativo Telegram."""
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendChatAction"
        requests.post(url, json={"chat_id": str(chat_id), "action": action}, timeout=4)
    except Exception:
        pass


# =========================================================================
# RUNNER DE LONG-POLLING DO BOT TELEGRAM PARA UM USUÁRIO
# =========================================================================

class TelegramBotRunner:
    """Gerencia a thread de polling e o processamento de comandos recebidos para um usuário."""
    
    def __init__(self, user_email: str, bot_token: str, chat_id: str = ""):
        self.user_email = user_email.strip().lower()
        self.bot_token = bot_token.strip()
        self.chat_id = str(chat_id or "").strip()
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.last_update_id = 0
        
    def start(self):
        if self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._polling_loop, daemon=True, name=f"TelegramBot-{self.user_email}")
        self.thread.start()
        system_logger.info(f"Bot do Telegram iniciado para o usuário: {self.user_email}")

    def stop(self):
        self.running = False
        system_logger.info(f"Parando Bot do Telegram para o usuário: {self.user_email}")

    def _polling_loop(self):
        system_logger.info(f"Loop de polling do Telegram ativo para: {self.user_email}")
        
        while self.running:
            try:
                url = f"https://api.telegram.org/bot{self.bot_token}/getUpdates"
                params = {
                    "offset": self.last_update_id + 1,
                    "timeout": 15,
                    "allowed_updates": ["message"]
                }
                
                resp = requests.get(url, params=params, timeout=25)
                if not self.running:
                    break
                    
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("ok"):
                        updates = data.get("result", [])
                        for update in updates:
                            update_id = update.get("update_id", 0)
                            if update_id > self.last_update_id:
                                self.last_update_id = update_id
                            self._handle_update(update)
                elif resp.status_code == 401:
                    system_logger.error(f"Token inválido do Telegram para usuário {self.user_email}. Encerrando polling.")
                    self.running = False
                    break
                else:
                    time.sleep(3)
            except requests.exceptions.Timeout:
                continue
            except Exception as e:
                if self.running:
                    system_logger.warning(f"Exceção no polling do Telegram ({self.user_email}): {e}")
                    time.sleep(5)

    def _handle_update(self, update: Dict[str, Any]):
        message = update.get("message")
        if not message:
            return
            
        incoming_chat_id = str(message.get("chat", {}).get("id", ""))
        from_user = message.get("from", {})
        first_name = from_user.get("first_name", "Usuário")
        text = (message.get("text") or "").strip()
        
        # 1. Se o chat_id não estava configurado ou o usuário enviou /start, auto-vincula
        if not self.chat_id or text == "/start":
            self.chat_id = incoming_chat_id
            db_save_telegram_config(
                user_email=self.user_email,
                bot_token=self.bot_token,
                chat_id=self.chat_id,
                enabled=True
            )
            welcome_msg = (
                f"👋 Olá, {first_name}!\n\n"
                f"Eu sou a **Sexta-Feira**, sua assistente de automação residencial inteligente.\n"
                f"Seu Telegram foi **vinculado com sucesso** à sua conta (`{self.user_email}`).\n\n"
                f"💡 **O que você pode fazer:**\n"
                f"• Controlar a casa: *'Ligue a luz da sala'*, *'Desligue tudo'*\n"
                f"• Ver as câmeras: envie `/camera` ou *'Quem está na sala?'*\n"
                f"• Consultar status: envie `/status` ou *'Quais luzes estão acesas?'*\n"
                f"• Gerenciar agenda: *'O que tenho hoje?'*, *'Agende reunião amanhã às 14h'*\n"
                f"• Tarefas & Keep: *'Adicione leite na lista de compras'*, *'Minhas tarefas'*\n"
                f"• E-mails: *'Tenho novos e-mails?'*, *'Envie um e-mail para...'* \n\n"
                f"Pode conversar comigo em linguagem natural a qualquer momento!"
            )
            send_telegram_message(self.bot_token, self.chat_id, welcome_msg)
            if text == "/start":
                return

        # Validação de segurança: apenas responde ao chat_id autorizado
        if self.chat_id and incoming_chat_id != self.chat_id:
            system_logger.warning(f"Mensagem do Telegram ignorada de chat não autorizado: {incoming_chat_id}")
            send_telegram_message(
                self.bot_token, 
                incoming_chat_id, 
                "⛔ Acesso não autorizado. Esta instância está vinculada a outro usuário."
            )
            return

        if not text:
            # Caso o usuário tenha enviado uma foto ou documento
            if message.get("photo"):
                send_telegram_chat_action(self.bot_token, self.chat_id, "typing")
                send_telegram_message(self.bot_token, self.chat_id, "📸 Foto recebida! Você pode me fazer perguntas sobre o ambiente ou câmeras da residência.")
            return

        system_logger.info(f"Comando Telegram recebido de {self.user_email} (Chat {incoming_chat_id}): '{text}'")

        # 2. Comandos Especiais Rápidos
        cmd = text.lower().strip()
        
        if cmd in ("/ajuda", "/help"):
            help_text = (
                "🤖 **Comandos da Sexta-Feira no Telegram:**\n\n"
                "• `/camera` ou `/foto` - Captura e envia a foto da câmera ao vivo\n"
                "• `/status` - Relatório rápido de status da residência\n"
                "• `/luzes_on` - Liga as luzes da residência\n"
                "• `/luzes_off` - Desliga todas as luzes\n\n"
                "Você também pode enviar **qualquer pergunta ou pedido em linguagem natural** (controle de luzes, quem está no cômodo, e-mails, agenda, tarefas e notas)."
            )
            send_telegram_message(self.bot_token, self.chat_id, help_text)
            return

        if cmd in ("/camera", "/foto", "foto da camera", "ver camera", "tirar foto"):
            send_telegram_chat_action(self.bot_token, self.chat_id, "upload_photo")
            frame_bytes, err = capture_camera_frame()
            if frame_bytes:
                caption = "📸 Captura ao vivo da Câmera Residencial."
                try:
                    # Análise rápida com IA
                    analysis = analyze_image_with_vision(frame_bytes, "Descreva em 1 ou 2 frases curtas o que está visível no cômodo.")
                    if analysis and not analysis.startswith("Não foi possível"):
                        caption = f"📸 {analysis}"
                except Exception:
                    pass
                send_telegram_photo(self.bot_token, self.chat_id, frame_bytes, caption)
            else:
                send_telegram_message(self.bot_token, self.chat_id, f"⚠️ Não foi possível acessar a câmera: {err or 'Sem sinal de vídeo'}")
            return

        if cmd == "/status":
            send_telegram_chat_action(self.bot_token, self.chat_id, "typing")
            status_msg = relatorio_status_casa.invoke({})
            send_telegram_message(self.bot_token, self.chat_id, f"🏠 **Status da Casa:**\n\n{status_msg}")
            return

        # 3. Processamento Completo pelo Agente Inteligente (LangChain)
        send_telegram_chat_action(self.bot_token, self.chat_id, "typing")
        
        try:
            try:
                from api.agent import processar_comando_agente
            except ImportError:
                from agent import processar_comando_agente

            # Carrega perfil, configurações de IA (do banco de dados) e histórico recente para o usuário
            prof = get_user_profile(self.user_email)
            ai_cfg = db_get_ai_config(self.user_email)
            api_key = (ai_cfg.get("api_key") or prof.get("api_key") or os.getenv("GEMINI_API_KEY") or os.getenv("OPENAI_API_KEY") or "").strip()
            model_name = (ai_cfg.get("ai_model") or prof.get("ai_model") or os.getenv("DEFAULT_MODEL", "gemini-2.5-flash-lite")).strip()
            chat_hist = get_chat_history(self.user_email, limit=5)
            
            if not api_key:
                system_logger.warning(f"Chave de API de IA não encontrada no banco de dados para {self.user_email}")
                send_telegram_message(
                    self.bot_token,
                    self.chat_id,
                    "⚠️ *Chave de API não configurada*\n\n"
                    "Nenhuma chave de API de IA (Gemini ou OpenAI) foi configurada para a sua conta no banco de dados.\n"
                    "Por favor, acesse o painel web em *⚙️ Configurações & Conexões* para salvar sua chave de API."
                )
                return

            broker_host = os.getenv("MQTT_BROKER", "test.mosquitto.org")
            broker_port = int(os.getenv("MQTT_PORT", "1883"))
            
            result = processar_comando_agente(
                pergunta=text,
                user_message=text,
                api_key=api_key,
                modelo=model_name,
                agent_name="Sexta-Feira",
                rooms=[],
                rooms_state={},
                broker_config={"broker": broker_host, "port": broker_port},
                user_email=self.user_email,
                user_profile=prof,
                chat_history=chat_hist
            )
            
            reply = result.get("reply", "Comando processado.") if isinstance(result, dict) else str(result)
            actions = result.get("actions", []) if isinstance(result, dict) else []
            
            # Persiste no histórico do SQLite
            try:
                save_chat_message(
                    user_email=self.user_email,
                    user_message=text,
                    agent_response=reply
                )
            except Exception as e_hist:
                system_logger.warning(f"Falha ao persistir interação do Telegram no histórico: {e_hist}")
            
            action_footer = ""
            if actions:
                action_strs = []
                for a in actions:
                    if isinstance(a, dict):
                        action_strs.append(f"• {a.get('room', 'Dispositivo')}: {a.get('action', '')}")
                    else:
                        action_strs.append(f"• {str(a)}")
                action_footer = "\n\n⚡ *Ações executadas:*\n" + "\n".join(action_strs)
                
            final_message = f"{reply}{action_footer}"
            send_telegram_message(self.bot_token, self.chat_id, final_message)
            
        except Exception as e_agent:
            system_logger.error(f"Erro ao processar comando Telegram pelo agente: {e_agent}")
            send_telegram_message(
                self.bot_token, 
                self.chat_id, 
                f"Desculpe, ocorreu uma instabilidade ao processar seu comando: {e_agent}"
            )


# =========================================================================
# GERENCIADOR GLOBAL DO SERVIÇO DE TELEGRAM (SINGLETON)
# =========================================================================

class TelegramServiceManager:
    """Gerenciador central para coordenar bots de múltiplos usuários em segundo plano."""
    
    def __init__(self):
        self._runners: Dict[str, TelegramBotRunner] = {}
        self._lock = threading.Lock()
        
    def start_bot_for_user(self, user_email: str, bot_token: str, chat_id: str = ""):
        clean_email = (user_email or "").strip().lower()
        clean_token = (bot_token or "").strip()
        if not clean_email or not clean_token:
            return
            
        with self._lock:
            if clean_email in self._runners:
                self._runners[clean_email].stop()
                
            runner = TelegramBotRunner(clean_email, clean_token, chat_id)
            self._runners[clean_email] = runner
            runner.start()
            
    def stop_bot_for_user(self, user_email: str):
        clean_email = (user_email or "").strip().lower()
        with self._lock:
            runner = self._runners.pop(clean_email, None)
            if runner:
                runner.stop()

    def restart_all_active_bots(self):
        """Lê todos os bots ativos no SQLite e inicia seus loops de polling."""
        active_bots = db_get_all_active_telegram_bots()
        system_logger.info(f"Sincronizando bots do Telegram ativos no SQLite ({len(active_bots)} encontrados)...")
        for b in active_bots:
            self.start_bot_for_user(
                user_email=b["user_email"],
                bot_token=b["bot_token"],
                chat_id=b["chat_id"]
            )


# Instância global do gerenciador
telegram_manager = TelegramServiceManager()

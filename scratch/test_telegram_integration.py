import os
import sys
import unittest
from unittest.mock import patch, MagicMock

# Ajusta path para importar o pacote api
sys.path.insert(0, "/home/marcio/Área de Trabalho/projetos_pessoais/casa_beta")

from api.database import (
    init_db,
    db_save_telegram_config,
    db_get_telegram_config,
    db_get_all_active_telegram_bots,
    db_save_ai_config,
    get_user_profile
)
from api.telegram_bot import (
    send_telegram_message,
    send_telegram_photo,
    get_telegram_bot_info,
    TelegramBotRunner,
    telegram_manager
)
from api.tools.telegram_tools import (
    enviar_mensagem_telegram,
    enviar_foto_telegram,
    set_telegram_context
)
from api.main import app
from fastapi.testclient import TestClient
from api.auth import create_access_token

class TestTelegramIntegration(unittest.TestCase):
    
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.test_email = "marciotg_test@exemplo.com"
        cls.test_token = "123456789:ABCdefGhIJKlmNoPQRstuvWxyz"
        cls.test_chat_id = "987654321"
        cls.auth_token = create_access_token(data={"sub": cls.test_email})
        cls.client = TestClient(app)

    def test_01_database_telegram_crud(self):
        """Testa salvar, recuperar e listar configurações de bot no SQLite."""
        # Salva
        res = db_save_telegram_config(
            user_email=self.test_email,
            bot_token=self.test_token,
            chat_id=self.test_chat_id,
            enabled=True,
            notify_camera=True,
            notify_tasks=True
        )
        self.assertTrue(res.get("configured"))
        self.assertEqual(res.get("bot_token"), self.test_token)
        self.assertEqual(res.get("chat_id"), self.test_chat_id)
        
        # Recupera
        cfg = db_get_telegram_config(self.test_email)
        self.assertTrue(cfg.get("configured"))
        self.assertEqual(cfg.get("bot_token"), self.test_token)
        self.assertEqual(cfg.get("chat_id"), self.test_chat_id)
        self.assertTrue(cfg.get("enabled"))
        
        # Lista ativos
        actives = db_get_all_active_telegram_bots()
        matching = [b for b in actives if b["user_email"] == self.test_email]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0]["bot_token"], self.test_token)
        print("✅ [Test 01] SQLite Database Telegram CRUD: OK")

    @patch("api.telegram_bot.requests.post")
    def test_02_send_telegram_message(self, mock_post):
        """Testa envio de mensagem formatada via Telegram Bot API."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ok": True, "result": {"message_id": 101}}
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        ok, msg = send_telegram_message(self.test_token, self.test_chat_id, "Olá Telegram!")
        self.assertTrue(ok)
        self.assertIn("sucesso", msg.lower())
        mock_post.assert_called_once()
        print("✅ [Test 02] send_telegram_message: OK")

    @patch("api.telegram_bot.requests.post")
    def test_03_send_telegram_photo(self, mock_post):
        """Testa envio de foto com legenda via Telegram Bot API."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"ok": True, "result": {"message_id": 102}}
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        dummy_bytes = b"fake_jpeg_bytes"
        ok, msg = send_telegram_photo(self.test_token, self.test_chat_id, dummy_bytes, "Foto teste")
        self.assertTrue(ok)
        mock_post.assert_called_once()
        print("✅ [Test 03] send_telegram_photo: OK")

    @patch("api.telegram_bot.requests.get")
    def test_04_get_telegram_bot_info(self, mock_get):
        """Testa validação de token com getMe."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "ok": True,
            "result": {"id": 123456, "is_bot": True, "first_name": "SextaFeiraBot", "username": "sexta_feira_bot"}
        }
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        info, err = get_telegram_bot_info(self.test_token)
        self.assertIsNotNone(info)
        self.assertEqual(info["username"], "sexta_feira_bot")
        print("✅ [Test 04] get_telegram_bot_info: OK")

    @patch("api.tools.telegram_tools.send_telegram_message")
    @patch("api.tools.telegram_tools.send_telegram_photo")
    @patch("api.tools.telegram_tools.capture_camera_frame")
    def test_05_agent_telegram_tools(self, mock_capture, mock_send_photo, mock_send_msg):
        """Testa ferramentas LangChain enviar_mensagem_telegram e enviar_foto_telegram."""
        set_telegram_context(user_email=self.test_email, bot_token=self.test_token, chat_id=self.test_chat_id)
        
        # enviar_mensagem_telegram
        mock_send_msg.return_value = (True, "103")
        res_msg = enviar_mensagem_telegram.invoke({"mensagem": "Alerta de segurança: movimento detectado"})
        self.assertIn("sucesso", res_msg)
        mock_send_msg.assert_called_once()

        # enviar_foto_telegram
        mock_capture.return_value = (b"fake_frame_bytes", None)
        mock_send_photo.return_value = (True, "104")
        res_photo = enviar_foto_telegram.invoke({"legenda": "Câmera da Sala"})
        self.assertIn("sucesso", res_photo)
        mock_send_photo.assert_called_once()
        print("✅ [Test 05] LangChain Telegram Tools: OK")

    def test_06_fastapi_endpoints(self):
        """Testa endpoints GET /api/user/telegram-config e POST /api/user/telegram-config."""
        headers = {"Authorization": f"Bearer {self.auth_token}"}
        
        # POST
        post_res = self.client.post(
            "/api/user/telegram-config",
            json={
                "bot_token": self.test_token,
                "chat_id": self.test_chat_id,
                "enabled": True,
                "notify_camera": True,
                "notify_tasks": True
            },
            headers=headers
        )
        self.assertEqual(post_res.status_code, 200)
        self.assertEqual(post_res.json()["status"], "success")

        # GET
        get_res = self.client.get("/api/user/telegram-config", headers=headers)
        self.assertEqual(get_res.status_code, 200)
        data = get_res.json()
        self.assertTrue(data["configured"])
        self.assertTrue(data["enabled"])
        self.assertEqual(data["chat_id"], self.test_chat_id)

        # GET /api/agent/status
        status_res = self.client.get("/api/agent/status", headers=headers)
        self.assertEqual(status_res.status_code, 200)
        tg_status = status_res.json()["integrations"]["telegram"]
        self.assertTrue(tg_status["connected"])
        self.assertTrue(tg_status["enabled"])
        self.assertEqual(tg_status["chat_id"], self.test_chat_id)
        print("✅ [Test 06] FastAPI Telegram Endpoints & Status: OK")

    @patch("api.main.get_telegram_bot_info")
    @patch("api.main.send_telegram_message")
    def test_07_fastapi_test_endpoint(self, mock_send, mock_info):
        """Testa POST /api/user/telegram-config/test."""
        headers = {"Authorization": f"Bearer {self.auth_token}"}
        mock_info.return_value = ({"first_name": "SextaFeiraBot", "username": "sexta_feira_bot"}, None)
        mock_send.return_value = (True, "105")

        test_res = self.client.post(
            "/api/user/telegram-config/test",
            json={"bot_token": self.test_token, "chat_id": self.test_chat_id},
            headers=headers
        )
        self.assertEqual(test_res.status_code, 200)
        self.assertTrue(test_res.json()["valid_token"])
        self.assertTrue(test_res.json()["message_sent"])
        print("✅ [Test 07] FastAPI Telegram Test Endpoint: OK")

    @patch("api.telegram_bot.send_telegram_message")
    @patch("api.agent.processar_comando_agente")
    def test_08_telegram_bot_runner_message_routing(self, mock_processar, mock_send):
        """Testa o processamento e roteamento de comandos via TelegramBotRunner."""
        db_save_ai_config(self.test_email, api_key=self.test_token, ai_model="gemini-2.5-flash-lite")
        runner = TelegramBotRunner(self.test_email, self.test_token, self.test_chat_id)
        
        # 1. Comando /start
        update_start = {
            "message": {
                "chat": {"id": int(self.test_chat_id)},
                "text": "/start",
                "from": {"first_name": "Marcio"}
            }
        }
        mock_send.return_value = (True, "106")
        runner._handle_update(update_start)
        mock_send.assert_called()

        # 2. Comando em linguagem natural -> processar_comando_agente
        mock_send.reset_mock()
        mock_processar.return_value = {"reply": "Luzes da sala foram ligadas com sucesso.", "actions": ["sala_ON"]}
        
        update_text = {
            "message": {
                "chat": {"id": int(self.test_chat_id)},
                "text": "Ligue as luzes da sala por favor",
                "from": {"first_name": "Marcio"}
            }
        }
        runner._handle_update(update_text)
        mock_processar.assert_called_once()
        expected_text = "Luzes da sala foram ligadas com sucesso.\n\n⚡ *Ações executadas:*\n• sala_ON"
        mock_send.assert_called_with(
            self.test_token,
            str(self.test_chat_id),
            expected_text
        )
        print("✅ [Test 08] TelegramBotRunner Command Routing: OK")


if __name__ == "__main__":
    unittest.main()

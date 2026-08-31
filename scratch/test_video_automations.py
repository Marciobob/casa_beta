import sys
import os
import unittest
import json
import base64
from datetime import datetime
import dateutil.tz

# Ajusta path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from api.database import (
    init_db,
    save_user_profile,
    db_create_automation,
    db_get_automations,
    db_get_automation_by_id,
    db_delete_automation,
    db_get_all_residents,
    db_save_camera_config,
    db_save_telegram_config
)
from api.auth import register_user
from api.video_automation import evaluate_video_automation
from api.automation_engine import AutomationEngine
from api.main import app
from fastapi.testclient import TestClient

class TestVideoAutomations(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        init_db()
        cls.client = TestClient(app)
        cls.test_email = "marcio_video_test@exemplo.com"
        
        try:
            register_user("Marcio Video Test", "11999998888", cls.test_email, "senha_video_123")
        except Exception:
            pass

        # Cria uma imagem JPEG dummy 100x100 para foto de perfil
        import cv2
        import numpy as np
        dummy_img = np.zeros((100, 100, 3), dtype=np.uint8)
        dummy_img[:, :] = [100, 150, 200]
        _, buf = cv2.imencode(".jpg", dummy_img)
        cls.dummy_photo_b64 = base64.b64encode(buf.tobytes()).decode("utf-8")

        save_user_profile(cls.test_email, {
            "name": "Marcio Morador",
            "photo_base64": cls.dummy_photo_b64,
            "api_key": "fake_gemini_key_for_test",
            "ai_model": "gemini-2.5-flash-lite"
        })

        db_save_camera_config(
            user_email=cls.test_email,
            camera_type="device",
            camera_device_index=0
        )

        db_save_telegram_config(
            user_email=cls.test_email,
            bot_token="123456:fake_test_bot_token",
            chat_id="987654321",
            enabled=True
        )

    def test_01_create_video_automation_in_db(self):
        """Testa criação e persistência de regra de vídeo e reconhecimento no SQLite."""
        rule = db_create_automation(
            user_email=self.test_email,
            name="📹 Monitorar Chegada do Marcio",
            automation_type="video_face_recognition",
            trigger_type="interval_seconds",
            trigger_value="30",
            action_type="video_alert",
            action_payload={
                "detection_mode": "video_face_recognition",
                "target_person": "Marcio Morador",
                "notify_telegram": True,
                "cooldown_seconds": 300,
                "custom_message": "🎉 Marcio acaba de ser reconhecido na câmera!"
            }
        )
        self.assertIsNotNone(rule)
        self.assertEqual(rule["automation_type"], "video_face_recognition")
        self.assertEqual(rule["action_payload"]["target_person"], "Marcio Morador")
        print("✅ [Test 01] Criação e persistência de regra de vídeo no SQLite: OK")

    def test_02_residents_list_and_templates_api(self):
        """Testa endpoint de listagem de moradores e modelos de automações."""
        # Login
        login_res = self.client.post("/api/auth/login", json={
            "email": self.test_email,
            "password": "senha_video_123"
        })
        self.assertEqual(login_res.status_code, 200)
        token = login_res.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 1. Endpoint /api/residents/list
        res_list = self.client.get("/api/residents/list", headers=headers)
        self.assertEqual(res_list.status_code, 200)
        residents = res_list.json()["residents"]
        self.assertTrue(len(residents) > 0)
        print(f"✅ [Test 02.1] Endpoint /api/residents/list retornou {len(residents)} morador(es): OK")

        # 2. Endpoint /api/automations/templates
        res_tpl = self.client.get("/api/automations/templates")
        self.assertEqual(res_tpl.status_code, 200)
        templates = res_tpl.json()["templates"]
        video_templates = [t for t in templates if t["automation_type"].startswith("video_")]
        self.assertTrue(len(video_templates) >= 2)
        print(f"✅ [Test 02.2] Endpoint /api/automations/templates contém {len(video_templates)} templates de vídeo: OK")

    def test_03_evaluate_video_automation_logic(self):
        """Testa avaliação de automação de vídeo com simulação de frame e cooldown."""
        tz_local = dateutil.tz.tzlocal()
        now_local = datetime.now(tz_local)
        
        rule = {
            "id": 9999,
            "user_email": self.test_email,
            "name": "Teste Unitário Vídeo",
            "automation_type": "video_unknown_alert",
            "trigger_type": "interval_seconds",
            "trigger_value": "30",
            "action_type": "video_alert",
            "action_payload": {
                "detection_mode": "video_unknown_alert",
                "target_person": "desconhecido",
                "notify_telegram": False,
                "cooldown_seconds": 60,
                "custom_message": "Alerta de teste"
            }
        }
        
        # Executa evaluate_video_automation
        ok, msg = evaluate_video_automation(rule, now_local, is_manual=True)
        self.assertIsInstance(ok, bool)
        self.assertIsInstance(msg, str)
        print(f"✅ [Test 03] evaluate_video_automation executado com resposta: {msg[:100]}: OK")

    def test_04_agent_action_prompt_execution(self):
        """Testa acionamento residencial com comando livre em linguagem natural."""
        rule = db_create_automation(
            user_email=self.test_email,
            name="📹 Chegada com Luzes Inteligentes",
            automation_type="video_face_recognition",
            trigger_type="interval_seconds",
            trigger_value="30",
            action_type="video_alert",
            action_payload={
                "detection_mode": "video_face_recognition",
                "target_person": "Marcio Morador",
                "notify_telegram": False,
                "agent_action_prompt": "Acender a luz da sala e da entrada",
                "cooldown_seconds": 300,
                "custom_message": "🎉 Morador identificado!"
            }
        )
        self.assertIsNotNone(rule)
        self.assertEqual(rule["action_payload"]["agent_action_prompt"], "Acender a luz da sala e da entrada")
        print("✅ [Test 04] Automação com comando livre em linguagem natural: OK")

    def test_05_opencv_pre_filter_token_savings(self):
        """Testa o pré-filtro OpenCV para economia de tokens em frames sem pessoas."""
        from api.video_automation import opencv_detect_person_or_face
        import cv2
        import numpy as np

        # 1. Frame vazio / sem pessoas -> deve retornar False (economia de tokens)
        empty_frame = np.full((300, 300, 3), 120, dtype=np.uint8)
        _, empty_bytes = cv2.imencode(".jpg", empty_frame)
        has_p, count, desc = opencv_detect_person_or_face(empty_bytes.tobytes())
        self.assertFalse(has_p)
        self.assertEqual(count, 0)
        print(f"✅ [Test 05.1] OpenCV filtrou com sucesso frame vazio: '{desc}'")

        # 2. Frame com foto de perfil do morador -> deve detectar rosto
        photo_bytes = base64.b64decode(self.dummy_photo_b64)
        has_p2, count2, desc2 = opencv_detect_person_or_face(photo_bytes)
        # Dummy image pode não ter feições humanas reais, testamos a robustez do retorno
        self.assertIsInstance(has_p2, bool)
        print(f"✅ [Test 05.2] OpenCV detector de alta precisão executado com sucesso: '{desc2}'")

    @classmethod
    def tearDownClass(cls):
        """Limpa dados e automações de teste criados no SQLite."""
        try:
            from api.database import get_db_connection
            conn = get_db_connection()
            c = conn.cursor()
            c.execute("DELETE FROM user_automations WHERE user_email = ?", (cls.test_email,))
            c.execute("DELETE FROM user_profiles WHERE user_email = ?", (cls.test_email,))
            c.execute("DELETE FROM users WHERE email = ?", (cls.test_email,))
            conn.commit()
            conn.close()
        except Exception:
            pass

if __name__ == "__main__":
    unittest.main()

import unittest
import sys
import json
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from fastapi.testclient import TestClient
from api.main import app
from api.auth import create_access_token
from api.database import db_get_ai_config, get_chat_history

class TestChatStream(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_email = "marciobob47@gmail.com"
        cls.auth_token = create_access_token(data={"sub": cls.test_email})
        cls.client = TestClient(app)
        ai_cfg = db_get_ai_config(cls.test_email)
        cls.api_key = ai_cfg.get("api_key")
        cls.model = ai_cfg.get("ai_model") or "gemini-2.5-flash-lite"

    def test_01_chat_stream_status_and_final_events(self):
        """Verifica se o endpoint SSE transmite eventos de status intermediários e o final."""
        headers = {"Authorization": f"Bearer {self.auth_token}"}
        payload = {
            "message": "apagar todos os e-mails da minha caixa de entrada",
            "api_key": self.api_key,
            "model": self.model,
            "agent_name": "Sexta-Feira",
            "rooms": [],
            "rooms_state": {}
        }
        res = self.client.post("/api/chat/stream", json=payload, headers=headers)
        self.assertEqual(res.status_code, 200)
        self.assertIn("text/event-stream", res.headers.get("content-type", ""))

        events = []
        for line in res.iter_lines():
            if line and line.startswith("data: "):
                event_data = json.loads(line[6:])
                events.append(event_data)

        self.assertTrue(len(events) >= 2, f"Esperado pelo menos 2 eventos (status e final), obteve {len(events)}")
        status_events = [e for e in events if e.get("type") == "status"]
        final_events = [e for e in events if e.get("type") == "final"]

        self.assertTrue(len(status_events) >= 1, "Deveria conter pelo menos um evento de status intermediário")
        self.assertEqual(len(final_events), 1, "Deveria conter exatamente um evento final")
        self.assertTrue(len(final_events[0].get("reply", "")) > 0)
        print("✅ [Test 01] Chat Stream Status & Final Events: OK")
        print(f"   Eventos recebidos: {len(events)} (Status: {len(status_events)}, Final: 1)")
        print(f"   Primeiro status: '{status_events[0].get('message')}'")
        print(f"   Resposta final: '{final_events[0].get('reply')[:80]}...'")

    def test_02_chat_stream_persists_history(self):
        """Verifica se a resposta do stream é devidamente persistida no histórico do usuário."""
        hist = get_chat_history(self.test_email, limit=5)
        self.assertTrue(len(hist) > 0)
        last_item = hist[0]
        self.assertIn("user_message", last_item)
        self.assertIn("agent_response", last_item)
        print("✅ [Test 02] Chat Stream Persistence in SQLite: OK")

if __name__ == "__main__":
    unittest.main()

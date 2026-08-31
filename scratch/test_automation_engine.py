import unittest
import os
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
import dateutil.tz

# Ajusta sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from fastapi.testclient import TestClient
from api.main import app
from api.database import (
    db_create_automation,
    db_get_automations,
    db_get_automation_by_id,
    db_update_automation,
    db_delete_automation,
    db_toggle_automation,
    db_get_all_active_automations,
    db_record_automation_run,
    db_is_event_already_notified,
    db_mark_event_notified,
    db_get_automations_count,
    db_save_google_credentials,
    db_save_telegram_config,
    db_save_ai_config
)
from api.auth import create_access_token
from api.automation_engine import automation_engine, run_automation_now, AutomationEngine

class TestAutomationEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_email = "marcio_auto_test@exemplo.com"
        cls.test_token = "999888777:ABC_auto_token"
        cls.test_chat_id = "8301234492"
        cls.auth_token = create_access_token(data={"sub": cls.test_email})
        cls.client = TestClient(app)

        # Salva credenciais de teste para o usuário no SQLite
        db_save_google_credentials(cls.test_email, "marciobob47@gmail.com", "eexlamongkpkimsq")
        db_save_telegram_config(cls.test_email, cls.test_token, cls.test_chat_id, enabled=True)
        db_save_ai_config(cls.test_email, api_key="AIzaSyTest_AutoKey123", ai_model="gemini-2.5-flash-lite")
        automation_engine.start()

    @classmethod
    def tearDownClass(cls):
        automation_engine.stop()
        import sqlite3
        conn = sqlite3.connect(root_dir / "api" / "smarthome.db")
        cur = conn.cursor()
        cur.execute("DELETE FROM user_automations WHERE user_email = ?", (cls.test_email,))
        cur.execute("DELETE FROM automation_notified_events WHERE user_email = ?", (cls.test_email,))
        cur.execute("DELETE FROM user_profiles WHERE user_email = ?", (cls.test_email,))
        conn.commit()
        conn.close()

    def test_01_automation_database_crud(self):
        """Testa criação, leitura, atualização, toggle e exclusão de automações no SQLite."""
        auto = db_create_automation(
            user_email=self.test_email,
            name="Lembrete de Reuniões 15min",
            automation_type="calendar_reminder",
            trigger_type="event_relative_minutes",
            trigger_value="15",
            action_type="telegram_alert",
            action_payload={"minutes_before": 15},
            is_enabled=True
        )
        self.assertIsNotNone(auto["id"])
        self.assertEqual(auto["name"], "Lembrete de Reuniões 15min")
        self.assertTrue(auto["is_enabled"])
        auto_id = auto["id"]

        # Busca por ID
        fetched = db_get_automation_by_id(self.test_email, auto_id)
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["automation_type"], "calendar_reminder")

        # Toggle
        toggled = db_toggle_automation(self.test_email, auto_id)
        self.assertFalse(toggled["is_enabled"])
        toggled = db_toggle_automation(self.test_email, auto_id)
        self.assertTrue(toggled["is_enabled"])

        # Deduplicação
        event_key = "test_event_999_20260830"
        self.assertFalse(db_is_event_already_notified(auto_id, event_key))
        db_mark_event_notified(auto_id, self.test_email, event_key)
        self.assertTrue(db_is_event_already_notified(auto_id, event_key))

        # Registro de execução
        db_record_automation_run(auto_id, "success", "1 alerta enviado no Telegram.")
        updated = db_get_automation_by_id(self.test_email, auto_id)
        self.assertEqual(updated["last_status"], "success")
        self.assertIn("1 alerta", updated["last_result"])

        print("✅ [Test 01] SQLite Automation Engine CRUD & Deduplication: OK")

    def test_02_fastapi_automation_endpoints(self):
        """Testa endpoints REST de automações no FastAPI."""
        headers = {"Authorization": f"Bearer {self.auth_token}"}

        # 1. GET /api/automations/templates
        res_tpl = self.client.get("/api/automations/templates")
        self.assertEqual(res_tpl.status_code, 200)
        templates = res_tpl.json()["templates"]
        self.assertGreaterEqual(len(templates), 4)

        # 2. POST /api/automations
        res_create = self.client.post(
            "/api/automations",
            json={
                "name": "Resumo Matinal 08:00",
                "automation_type": "daily_summary",
                "trigger_type": "daily_time",
                "trigger_value": "08:00",
                "action_type": "telegram_alert",
                "action_payload": {},
                "is_enabled": True
            },
            headers=headers
        )
        self.assertEqual(res_create.status_code, 200)
        auto = res_create.json()["automation"]
        auto_id = auto["id"]

        # 3. GET /api/automations
        res_list = self.client.get("/api/automations", headers=headers)
        self.assertEqual(res_list.status_code, 200)
        data = res_list.json()
        self.assertGreaterEqual(len(data["automations"]), 1)
        self.assertTrue(data["engine_running"])

        # 4. PATCH /api/automations/{id}/toggle
        res_toggle = self.client.patch(f"/api/automations/{auto_id}/toggle", headers=headers)
        self.assertEqual(res_toggle.status_code, 200)
        self.assertFalse(res_toggle.json()["automation"]["is_enabled"])

        # 5. DELETE /api/automations/{id}
        res_del = self.client.delete(f"/api/automations/{auto_id}", headers=headers)
        self.assertEqual(res_del.status_code, 200)
        print("✅ [Test 02] FastAPI Automation REST Endpoints: OK")

    @patch("api.automation_engine.send_telegram_message")
    @patch("api.automation_engine.connect_caldav")
    def test_03_calendar_reminder_execution_and_deduplication(self, mock_caldav, mock_send):
        """Testa o disparo de alerta da Google Agenda com deduplicação para o Telegram."""
        tz_local = dateutil.tz.tzlocal()
        now_local = datetime.now(tz_local)
        
        # Cria automação de lembrete
        auto = db_create_automation(
            user_email=self.test_email,
            name="Lembrete Consulta Médica 15min",
            automation_type="calendar_reminder",
            trigger_type="event_relative_minutes",
            trigger_value="15",
            action_type="telegram_alert",
            action_payload={"minutes_before": 15},
            is_enabled=True
        )
        auto_id = auto["id"]

        # Simula mock de evento da agenda começando em 12 minutos
        start_event = now_local + timedelta(minutes=12)
        mock_cal = MagicMock()
        mock_event = MagicMock()
        
        # Mock do formatar_evento
        with patch("api.automation_engine.formatar_evento") as mock_format:
            mock_format.return_value = {
                "id": "event_medico_123",
                "titulo": "Consulta Cardiológica",
                "inicio": start_event.strftime("%H:%M"),
                "local": "Hospital Central",
                "descricao": "Levar exames de sangue",
                "raw_dtstart": start_event
            }
            mock_cal.search.return_value = [mock_event]
            mock_caldav.return_value = (mock_cal, None)
            mock_send.return_value = (True, "101")

            engine = AutomationEngine(check_interval_seconds=30)
            
            # 1ª Execução: deve enviar mensagem no Telegram
            ok, msg = engine.execute_calendar_reminder(auto, now_local)
            self.assertTrue(ok)
            mock_send.assert_called_once()
            called_text = mock_send.call_args[0][2]
            self.assertIn("Consulta Cardiológica", called_text)
            self.assertIn("Hospital Central", called_text)
            self.assertIn("Levar exames de sangue", called_text)

            # 2ª Execução: evento já notificado, não deve enviar duplicata
            mock_send.reset_mock()
            ok2, msg2 = engine.execute_calendar_reminder(auto, now_local)
            self.assertTrue(ok2)
            mock_send.assert_not_called()
            print("✅ [Test 03] Calendar Reminder Telegram Alert & Deduplication: OK")

    @patch("api.automation_engine.send_telegram_message")
    def test_04_daily_summary_execution(self, mock_send):
        """Testa geração do resumo matinal/diário enviado ao Telegram."""
        mock_send.return_value = (True, "102")
        auto = db_create_automation(
            user_email=self.test_email,
            name="Resumo do Dia",
            automation_type="daily_summary",
            trigger_type="daily_time",
            trigger_value="08:00",
            action_type="telegram_alert",
            action_payload={},
            is_enabled=True
        )
        
        engine = AutomationEngine(check_interval_seconds=30)
        ok, msg = engine.execute_automation_action(auto, is_manual=True)
        self.assertTrue(ok)
        mock_send.assert_called_once()
        called_text = mock_send.call_args[0][2]
        self.assertIn("Resumo do Dia", called_text)
        print("✅ [Test 04] Daily Morning Summary Telegram Dispatch: OK")

    @patch("api.automation_engine.controlar_luzes")
    @patch("api.automation_engine.send_telegram_message")
    def test_05_mqtt_schedule_and_custom_prompt(self, mock_send, mock_mqtt):
        """Testa agendamento de iluminação MQTT e envio de confirmação."""
        mock_mqtt.invoke.return_value = "Lâmpadas de todas desligadas via MQTT."
        mock_send.return_value = (True, "103")

        auto_mqtt = db_create_automation(
            user_email=self.test_email,
            name="Apagar Luzes Noturnas",
            automation_type="mqtt_schedule",
            trigger_type="daily_time",
            trigger_value="23:30",
            action_type="mqtt_command",
            action_payload={"room": "todas", "action": "OFF", "notify_telegram": True},
            is_enabled=True
        )

        engine = AutomationEngine(check_interval_seconds=30)
        ok, msg = engine.execute_automation_action(auto_mqtt, is_manual=True)
        self.assertTrue(ok)
        mock_mqtt.invoke.assert_called_with({"room": "todas", "action": "OFF"})
        mock_send.assert_called_once()
        print("✅ [Test 05] MQTT Scheduled Automation: OK")

    @patch("api.automation_engine.send_telegram_message")
    def test_06_manual_run_endpoint(self, mock_send):
        """Testa a execução imediata sob demanda através da rota POST /api/automations/{id}/run."""
        mock_send.return_value = (True, "104")
        auto = db_create_automation(
            user_email=self.test_email,
            name="Aviso Teste Manual",
            automation_type="daily_summary",
            trigger_type="daily_time",
            trigger_value="09:00",
            action_type="telegram_alert",
            action_payload={},
            is_enabled=True
        )
        
        headers = {"Authorization": f"Bearer {self.auth_token}"}
        res_run = self.client.post(f"/api/automations/{auto['id']}/run", headers=headers)
        self.assertEqual(res_run.status_code, 200)
        self.assertTrue(res_run.json()["executed"])
        print("✅ [Test 06] Manual Run Endpoint (/run): OK")


if __name__ == "__main__":
    unittest.main()

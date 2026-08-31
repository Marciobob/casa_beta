import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime, date, timedelta
import sys
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from api.tools.calendar_tools import (
    listar_compromissos,
    agendar_compromisso,
    cancelar_compromisso,
    parse_data_relativa,
    set_calendar_credentials_context,
    get_calendar_credentials,
    connect_caldav
)

class TestCalendarTools(unittest.TestCase):
    def test_01_parse_data_relativa(self):
        hoje = datetime.now().date()
        self.assertEqual(parse_data_relativa("hoje"), hoje)
        self.assertEqual(parse_data_relativa("amanhã"), hoje + timedelta(days=1))
        self.assertEqual(parse_data_relativa("depois de amanhã"), hoje + timedelta(days=2))
        self.assertEqual(parse_data_relativa("2026-08-30"), date(2026, 8, 30))
        print("✅ [Test 01] Calendar Date Parsing: OK")

    def test_02_credentials_context(self):
        set_calendar_credentials_context("test@gmail.com", "abcd efgh ijkl mnop")
        u, p = get_calendar_credentials()
        self.assertEqual(u, "test@gmail.com")
        self.assertEqual(p, "abcdefghijklmnop")
        print("✅ [Test 02] Calendar Credentials Context: OK")

    @patch("api.tools.calendar_tools.connect_caldav")
    def test_03_listar_compromissos_mock(self, mock_connect):
        mock_cal = MagicMock()
        mock_event = MagicMock()
        
        # Simula o componente icalendar
        mock_comp = MagicMock()
        mock_comp.get.side_effect = lambda k, default=None: {
            "summary": "Consulta Médica",
            "dtstart": MagicMock(dt=datetime(2026, 8, 30, 14, 0)),
            "dtend": MagicMock(dt=datetime(2026, 8, 30, 15, 0)),
            "description": "Revisão anual",
            "location": "Consultório Central",
            "uid": "event-12345"
        }.get(k, default)
        
        mock_event.icalendar_component = mock_comp
        mock_cal.search.return_value = [mock_event]
        mock_connect.return_value = (mock_cal, None)

        res = listar_compromissos.invoke({"dias": 7})
        self.assertIn("Consulta Médica", res)
        self.assertIn("14:00", res)
        print("✅ [Test 03] Listar Compromissos (Mock): OK")

    @patch("api.tools.calendar_tools.connect_caldav")
    def test_04_agendar_compromisso_mock(self, mock_connect):
        mock_cal = MagicMock()
        mock_connect.return_value = (mock_cal, None)

        res = agendar_compromisso.invoke({
            "titulo": "Reunião de Equipe",
            "data_inicio": "amanhã",
            "hora_inicio": "10:00",
            "duracao_minutos": 60,
            "descricao": "Planejamento",
            "localizacao": "Sala 1"
        })
        self.assertIn("Sucesso: O compromisso 'Reunião de Equipe' foi agendado", res)
        print("✅ [Test 04] Agendar Compromisso (Mock): OK")

if __name__ == "__main__":
    unittest.main()

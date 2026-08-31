import unittest
import sys
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from api.tools.gmail_tools import apagar_email, apagar_todos_emails, set_gmail_credentials_context, ler_emails_recentes
from api.database import db_get_google_credentials
from api.agent import processar_comando_agente
from api.database import db_get_ai_config

class TestGmailDeletion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.user_email = "marciobob47@gmail.com"
        gmail_user, gmail_pwd = db_get_google_credentials(cls.user_email)
        set_gmail_credentials_context(gmail_user, gmail_pwd)
        ai_cfg = db_get_ai_config(cls.user_email)
        cls.api_key = ai_cfg.get("api_key")
        cls.model = ai_cfg.get("ai_model") or "gemini-2.5-flash-lite"

    def test_01_tool_apagar_email_flexibility(self):
        """Verifica que apagar_email lida com 'todos' ou palavras-chave graciosamente sem quebrar."""
        res = apagar_email.invoke({"id_ou_assunto_email": "assunto_inexistente_xyz_12345"})
        print("Result for nonexistent:", res)
        self.assertIn("Não foi possível encontrar", res)

    def test_02_tool_apagar_todos_emails(self):
        """Testa a execução de apagar_todos_emails."""
        res = apagar_todos_emails.invoke({"confirmacao": "sim"})
        print("Result apagar_todos_emails:", res)
        self.assertTrue("Sucesso" in res or "vazia" in res)

    def test_03_agent_processes_apagar_todos_emails(self):
        """Testa o agente interpretando o comando de voz 'apagar todos os e-mails'."""
        resultado = processar_comando_agente(
            pergunta="apagar todos os e-mails da minha caixa de entrada",
            api_key=self.api_key,
            modelo=self.model,
            agent_name="Sexta-Feira",
            rooms=[],
            rooms_state={},
            broker_config={"broker": "test.mosquitto.org", "port": 1883},
            user_email=self.user_email
        )
        print("Agent reply:", resultado.get("reply"))
        self.assertTrue(len(resultado.get("reply", "")) > 5)

if __name__ == "__main__":
    unittest.main()

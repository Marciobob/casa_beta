import unittest
import sys
from pathlib import Path

root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from fastapi.testclient import TestClient
from api.main import app
from api.database import (
    db_save_google_credentials,
    db_get_google_credentials
)
from api.auth import create_access_token

class TestGoogleCredentialsFlow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_email = "marciobob47@gmail.com"
        cls.auth_token = create_access_token(data={"sub": cls.test_email})
        cls.client = TestClient(app)

    def test_01_save_and_retrieve_credentials(self):
        """Testa salvar a nova senha e recuperar com máscara."""
        headers = {"Authorization": f"Bearer {self.auth_token}"}
        
        # 1. Salva a senha válida
        res_post = self.client.post(
            "/api/user/google-credentials",
            json={"gmail_email": self.test_email, "gmail_app_password": "eexlamongkpkimsq"},
            headers=headers
        )
        self.assertEqual(res_post.status_code, 200)
        self.assertTrue(res_post.json()["configured"])

        # 2. GET verifica se o endpoint retorna configured=True e senha mascarada
        res_get = self.client.get("/api/user/google-credentials", headers=headers)
        self.assertEqual(res_get.status_code, 200)
        data = res_get.json()
        self.assertTrue(data["configured"])
        self.assertEqual(data["gmail_email"], self.test_email)
        self.assertIn("ee", data["masked_password"])

        print("✅ [Test 01] Save & Retrieve Google Credentials: OK")

    def test_02_preserve_existing_password_on_empty_or_masked(self):
        """Garante que ao salvar sem preencher a senha novamente, a senha anterior é preservada no SQLite."""
        headers = {"Authorization": f"Bearer {self.auth_token}"}

        # 1. Envia requisição com senha mascarada
        res_post_masked = self.client.post(
            "/api/user/google-credentials",
            json={"gmail_email": self.test_email, "gmail_app_password": "••••••••••••••••"},
            headers=headers
        )
        self.assertEqual(res_post_masked.status_code, 200)

        # 2. Verifica no SQLite se a senha real permanece intacta
        email, pwd = db_get_google_credentials(self.test_email)
        self.assertEqual(pwd, "eexlamongkpkimsq")

        # 3. Envia requisição com senha vazia
        res_post_empty = self.client.post(
            "/api/user/google-credentials",
            json={"gmail_email": self.test_email, "gmail_app_password": ""},
            headers=headers
        )
        self.assertEqual(res_post_empty.status_code, 200)

        # 4. Verifica novamente
        email, pwd = db_get_google_credentials(self.test_email)
        self.assertEqual(pwd, "eexlamongkpkimsq")

        print("✅ [Test 02] Password Preservation on Empty/Masked Update: OK")

    def test_03_live_google_connectivity_endpoint(self):
        """Testa o endpoint /api/user/google-credentials/test com a senha salva."""
        headers = {"Authorization": f"Bearer {self.auth_token}"}
        res_test = self.client.post(
            "/api/user/google-credentials/test",
            json={"gmail_email": self.test_email, "gmail_app_password": "eexlamongkpkimsq"},
            headers=headers
        )
        self.assertEqual(res_test.status_code, 200)
        data = res_test.json()
        self.assertTrue(data["success"])
        self.assertTrue(data["imap"])
        self.assertTrue(data["caldav"])
        print("✅ [Test 03] Live Google Connectivity (IMAP + CalDAV): OK")

if __name__ == "__main__":
    unittest.main()

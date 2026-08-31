import unittest
import os
import sys
from pathlib import Path

# Ajusta sys.path
root_dir = Path(__file__).resolve().parent.parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from fastapi.testclient import TestClient
from api.main import app
from api.database import (
    db_save_ai_config,
    db_get_ai_config
)
from api.auth import create_access_token

class TestVoicePersistence(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_email = "marcio_voice_test@exemplo.com"
        cls.auth_token = create_access_token(data={"sub": cls.test_email})
        cls.client = TestClient(app)

    def test_01_sqlite_voice_persistence(self):
        """Testa salvar e recuperar vozes diferentes no banco de dados SQLite."""
        # 1. Salva Antonio
        db_save_ai_config(self.test_email, api_key="AIzaSyTestKey", ai_model="gemini-2.5-flash-lite", voice="pt-BR-AntonioNeural")
        cfg1 = db_get_ai_config(self.test_email)
        self.assertEqual(cfg1["voice"], "pt-BR-AntonioNeural")

        # 2. Atualiza para Thalita
        db_save_ai_config(self.test_email, voice="pt-BR-ThalitaMultilingualNeural")
        cfg2 = db_get_ai_config(self.test_email)
        self.assertEqual(cfg2["voice"], "pt-BR-ThalitaMultilingualNeural")
        # Garante que modelo e chave foram preservados
        self.assertEqual(cfg2["ai_model"], "gemini-2.5-flash-lite")
        self.assertEqual(cfg2["api_key"], "AIzaSyTestKey")

        # 3. Atualiza para browser-native
        db_save_ai_config(self.test_email, voice="browser-native")
        cfg3 = db_get_ai_config(self.test_email)
        self.assertEqual(cfg3["voice"], "browser-native")

        print("✅ [Test 01] SQLite Voice Persistence CRUD: OK")

    def test_02_fastapi_ai_config_voice_endpoints(self):
        """Testa endpoints REST GET e POST /api/user/ai-config para troca de voz."""
        headers = {"Authorization": f"Bearer {self.auth_token}"}

        # 1. POST alterando para Antonio
        res_post = self.client.post(
            "/api/user/ai-config",
            json={
                "api_key": "AIzaSyTestKey",
                "ai_model": "gemini-2.5-flash-lite",
                "voice": "pt-BR-AntonioNeural"
            },
            headers=headers
        )
        self.assertEqual(res_post.status_code, 200)
        self.assertEqual(res_post.json()["config"]["voice"], "pt-BR-AntonioNeural")

        # 2. GET simulando recarregamento da página (syncUserAiConfig)
        res_get = self.client.get("/api/user/ai-config", headers=headers)
        self.assertEqual(res_get.status_code, 200)
        self.assertEqual(res_get.json()["voice"], "pt-BR-AntonioNeural")

        # 3. POST auto-save de voz (quando o usuário muda apenas o select)
        res_post2 = self.client.post(
            "/api/user/ai-config",
            json={
                "voice": "pt-BR-ThalitaMultilingualNeural"
            },
            headers=headers
        )
        self.assertEqual(res_post2.status_code, 200)
        self.assertEqual(res_post2.json()["config"]["voice"], "pt-BR-ThalitaMultilingualNeural")

        # 4. Novo GET confirmando que a voz Thalita permanece persistida
        res_get2 = self.client.get("/api/user/ai-config", headers=headers)
        self.assertEqual(res_get2.status_code, 200)
        self.assertEqual(res_get2.json()["voice"], "pt-BR-ThalitaMultilingualNeural")

        print("✅ [Test 02] FastAPI /api/user/ai-config Voice Endpoints: OK")

    def test_03_static_frontend_files_integrity(self):
        """Verifica se index.html e casa.html possuem as diretivas de auto-save e sincronização."""
        static_dir = root_dir / "api" / "static"
        
        for filename in ["index.html", "casa.html"]:
            filepath = static_dir / filename
            self.assertTrue(filepath.exists(), f"{filename} deve existir")
            content = filepath.read_text(encoding="utf-8")

            # Verifica onchange no select
            self.assertIn('modalVoiceSelect" onchange="handleVoiceSelectChange', content, f"{filename} deve ter onchange no modalVoiceSelect")
            # Verifica função handleVoiceSelectChange
            self.assertIn("function handleVoiceSelectChange", content, f"{filename} deve conter handleVoiceSelectChange")
            # Verifica função syncUserAiConfig
            self.assertIn("async function syncUserAiConfig", content, f"{filename} deve conter syncUserAiConfig")
            # Verifica chamada de syncUserAiConfig
            self.assertIn("syncUserAiConfig()", content, f"{filename} deve chamar syncUserAiConfig()")
            # Verifica que não há tokens quebrados
            self.assertNotIn("smartHomeAuthToken", content, f"{filename} não deve conter smartHomeAuthToken quebrado")

        print("✅ [Test 03] Static Frontend Files Voice Integrity: OK")

if __name__ == "__main__":
    unittest.main()

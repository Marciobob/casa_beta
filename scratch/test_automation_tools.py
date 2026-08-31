import os
import sys
from pathlib import Path
import unittest
import base64

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from api.database import (
    get_db_connection,
    save_user_profile,
    db_get_automations,
    db_create_automation,
    db_delete_automation,
    get_user_profile,
    db_get_ai_config
)
from api.tools.automation_tools import (
    listar_automacoes,
    controlar_automacao,
    criar_automacao,
    excluir_automacao,
    executar_automacao_agora,
    set_automation_context
)
from api.agent import processar_comando_agente


class TestAutomationTools(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.test_email = "marcio_auto_tool_test@exemplo.com"
        save_user_profile(cls.test_email, {"name": "Marcio Teste Automação"})
        set_automation_context(cls.test_email)

        # Cria uma regra inicial de teste
        cls.rule1 = db_create_automation(
            user_email=cls.test_email,
            name="Regra de Teste Quarto",
            automation_type="video_face_recognition",
            trigger_type="interval_seconds",
            trigger_value="15",
            action_type="video_alert",
            action_payload={"agent_action_prompt": "acender luz do quarto 1", "target_person": "todos"},
            is_enabled=True
        )

    def test_01_listar_automacoes_tool(self):
        """Testa listagem de automações via tool."""
        res = listar_automacoes.invoke({})
        self.assertIn("Regra de Teste Quarto", res)
        self.assertIn("Reconhecimento Facial", res)
        self.assertIn("Ativa", res)
        print(f"✅ [Test 01] listar_automacoes executado com sucesso: {res[:80]}...")

    def test_02_controlar_automacao_desativar_e_ativar(self):
        """Testa desativação e reativação de automação via ID e Nome."""
        rule_id = str(self.rule1["id"])

        # 1. Desativa por ID
        res_desat = controlar_automacao.invoke({"identificador": rule_id, "acao": "desativar"})
        self.assertIn("desativada com sucesso", res_desat)
        
        # Verifica no banco
        autos = db_get_automations(self.test_email)
        target = [a for a in autos if a["id"] == self.rule1["id"]][0]
        self.assertFalse(target["is_enabled"])
        print(f"✅ [Test 02.1] Desativação por ID ({rule_id}): OK")

        # 2. Ativa por Nome
        res_at = controlar_automacao.invoke({"identificador": "Regra de Teste Quarto", "acao": "ativar"})
        self.assertIn("ativada com sucesso", res_at)

        autos = db_get_automations(self.test_email)
        target = [a for a in autos if a["id"] == self.rule1["id"]][0]
        self.assertTrue(target["is_enabled"])
        print(f"✅ [Test 02.2] Reativação por Nome ('Regra de Teste Quarto'): OK")

    def test_03_criar_e_excluir_automacao_tool(self):
        """Testa criação e exclusão de automação via tool."""
        res_create = criar_automacao.invoke({
            "nome": "☀️ Resumo das 08h",
            "tipo": "daily_summary",
            "gatilho_valor": "08:00"
        })
        self.assertIn("criada e ativada com sucesso", res_create)
        print(f"✅ [Test 03.1] Criação via tool: {res_create}")

        # Exclui
        res_del = excluir_automacao.invoke({"identificador": "☀️ Resumo das 08h"})
        self.assertIn("excluída com sucesso", res_del)
        print(f"✅ [Test 03.2] Exclusão via tool: {res_del}")

    def test_04_agent_natural_language_control(self):
        """Testa o agente completo interpretando comando em linguagem natural para controlar automações."""
        user_prof = get_user_profile("marciobob47@gmail.com")
        ai_cfg = db_get_ai_config("marciobob47@gmail.com")
        api_key = (ai_cfg.get("api_key") or user_prof.get("api_key") or "").strip()
        model_name = (ai_cfg.get("ai_model") or user_prof.get("ai_model") or "gemini-2.5-flash-lite").strip()

        if not api_key:
            print("⚠️ [Test 04] Pulando teste do agente (chave de API não configurada)")
            return

        set_automation_context(self.test_email)
        res = processar_comando_agente(
            pergunta="Quais são as minhas automações cadastradas no sistema?",
            api_key=api_key,
            modelo=model_name,
            agent_name="Sexta-Feira",
            user_email=self.test_email,
            user_profile=user_prof
        )
        reply = res.get("reply", "")
        self.assertTrue(len(reply) > 5)
        print(f"✅ [Test 04] Resposta do agente em linguagem natural: '{reply}'")

    @classmethod
    def tearDownClass(cls):
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("DELETE FROM user_automations WHERE user_email = ?", (cls.test_email,))
        c.execute("DELETE FROM user_profiles WHERE user_email = ?", (cls.test_email,))
        conn.commit()
        conn.close()


if __name__ == "__main__":
    unittest.main()

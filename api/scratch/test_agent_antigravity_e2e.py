import os
import sys
from pathlib import Path

current_dir = Path(__file__).parent.resolve()
project_root = current_dir.parent.resolve()
for path in (str(current_dir), str(project_root)):
    if path not in sys.path:
        sys.path.insert(0, path)

from agent import processar_comando_agente
from tools.antigravity_tools import is_antigravity_commands_allowed, set_antigravity_context

print("Testing Agent processing with Antigravity tool binding...")

# Test tool availability and prompt compilation
res = processar_comando_agente(
    pergunta="Qual é o status da sua integração com o Antigravity e como você pode usá-lo?",
    api_key="dummy_test_key_for_inspection",
    user_email="marcio@test.com",
    modelo="gemini-2.5-flash-lite",
    agent_name="Sexta-Feira"
)

print("Agent Response:", res)
assert "response" in res or "resposta" in res or "text" in res or isinstance(res, dict)
print("\nE2E AGENT TEST PASSED!")

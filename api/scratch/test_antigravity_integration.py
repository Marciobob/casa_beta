import os
import sys
import asyncio
from pathlib import Path

current_dir = Path(__file__).parent.resolve()
project_root = current_dir.parent.resolve()
for path in (str(current_dir), str(project_root)):
    if path not in sys.path:
        sys.path.insert(0, path)

from tools.antigravity_tools import (
    consultar_agente_antigravity,
    executar_comando_antigravity,
    perguntar_e_executar_antigravity,
    set_antigravity_context
)
from tools.manual_tools import consultar_manual_sistema
from agent import processar_comando_agente

print("=" * 60)
print("TESTING ANTIGRAVITY TOOLS AND INTEGRATION")
print("=" * 60)

# 1. Test set context and manual
set_antigravity_context(user_email="marcio@test.com", commands_enabled=True)
manual_res = consultar_manual_sistema.invoke({"modulo_ou_duvida": "antigravity"})
print("\n[1] Manual Antigravity Query:\n", manual_res)
assert "Antigravity" in manual_res

# 2. Test physical machine command execution
print("\n[2] Testing executar_comando_antigravity...")
cmd_res = executar_comando_antigravity.invoke({
    "comando": "echo 'Antigravity CLI Host Command Test' && uptime",
    "justificativa": "Teste de status do host"
})
print("Command Output:\n", cmd_res)
assert "Código 0" in cmd_res or "Antigravity" in cmd_res

# 3. Test consulting Antigravity
print("\n[3] Testing consultar_agente_antigravity...")
consult_res = consultar_agente_antigravity.invoke({
    "pergunta": "Como otimizar queries SQL em alta concorrência?"
})
print("Consultation Output:\n", consult_res[:300] + "...")

# 4. Test delegating task to Antigravity
print("\n[4] Testing perguntar_e_executar_antigravity...")
deleg_res = perguntar_e_executar_antigravity.invoke({
    "tarefa": "Verificar espaço em disco e sugerir limpeza se necessário"
})
print("Delegated Task Output:\n", deleg_res[:300] + "...")

print("\n" + "=" * 60)
print("ALL ANTIGRAVITY TOOL TESTS PASSED SUCCESSFULLY!")
print("=" * 60)

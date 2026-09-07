import os
import sys
from pathlib import Path

current_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(current_dir))

from tools.osint_tools import (
    clean_target_username,
    get_sherlock_executable,
    get_holehe_executable,
    run_dns_dig_scan,
    investigar_pessoa_osint,
    buscar_usuario_redes_sociais_sherlock,
    verificar_email_osint_holehe
)

def test_osint():
    print("=== TESTE OSINT ===")
    print("1. Limpeza de arroba/URL:", clean_target_username("@marcio_dev"))
    print("2. Sherlock path:", get_sherlock_executable())
    print("3. Holehe path:", get_holehe_executable())
    
    # Teste DNS
    print("4. Teste DNS (google.com):")
    dns_res = run_dns_dig_scan("google.com")
    print("   DNS Res:", dns_res)
    
    # Teste de ferramenta LangChain
    print("\n5. Testando buscar_usuario_redes_sociais_sherlock com username de teste rápido...")
    # Executa com usuário inválido para testar validação rápida
    res_invalido = buscar_usuario_redes_sociais_sherlock.invoke({"usuario_ou_arroba": ""})
    print("   Resultado entrada vazia:", res_invalido)

    print("\n6. Testando verificar_email_osint_holehe com email...")
    res_holehe = verificar_email_osint_holehe.invoke({"email": "invalid_email_format"})
    print("   Resultado email inválido:", res_holehe)

    print("\n=== SUCESSO NOS TESTES BÁSICOS DE OSINT ===")

if __name__ == "__main__":
    test_osint()

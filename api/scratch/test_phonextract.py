import sys
import os

# Adiciona o diretório raiz ao sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.osint_tools import (
    extrair_info_telefone_phonextract,
    investigar_telefone_phonextract
)

def test_phonextract_scenarios():
    print("=" * 60)
    print("TESTE 1: Celular Brasileiro (São Paulo - DDD 11)")
    print("=" * 60)
    res1 = extrair_info_telefone_phonextract("(11) 98765-4321")
    print(f"Sucesso: {res1.get('success')}")
    print(f"E.164: {res1.get('e164')}")
    print(f"Nacional: {res1.get('national_format')}")
    print(f"Internacional: {res1.get('international_format')}")
    print(f"País: {res1.get('country_name')}")
    print(f"Localização: {res1.get('location')}")
    print(f"Operadora: {res1.get('carrier')}")
    print(f"Tipo Linha: {res1.get('line_type')}")
    print(f"WhatsApp URL: {res1.get('whatsapp_url')}")
    assert res1.get("is_valid") == True
    assert "São Paulo" in res1.get("location")
    assert res1.get("country_code") == "55"
    assert "https://wa.me/5511987654321" in res1.get("whatsapp_url")

    print("\n" + "=" * 60)
    print("TESTE 2: Telefone Fixo Brasileiro (Rio de Janeiro - DDD 21)")
    print("=" * 60)
    res2 = extrair_info_telefone_phonextract("(21) 2234-5678")
    print(f"Sucesso: {res2.get('success')}")
    print(f"Localização: {res2.get('location')}")
    print(f"Tipo: {res2.get('line_type')}")
    assert res2.get("is_valid") == True
    assert "Rio de Janeiro" in res2.get("location")
    assert "Fixo" in res2.get("line_type")

    print("\n" + "=" * 60)
    print("TESTE 3: Telefone Internacional (EUA - Califórnia)")
    print("=" * 60)
    res3 = extrair_info_telefone_phonextract("+1 415 555 2671")
    print(f"Sucesso: {res3.get('success')}")
    print(f"País: {res3.get('country_name')}")
    print(f"Localização: {res3.get('location')}")
    print(f"E.164: {res3.get('e164')}")
    assert res3.get("country_code") == "1"
    assert res3.get("iso_region") == "US"

    print("\n" + "=" * 60)
    print("TESTE 4: Invocação da Ferramenta LangChain investigar_telefone_phonextract")
    print("=" * 60)
    report = investigar_telefone_phonextract.invoke({"numero_telefone": "(31) 99876-5432"})
    print(report)
    assert "PhoneXtract" in report
    assert "Minas Gerais" in report or "Belo Horizonte" in report
    assert "wa.me" in report

    print("\n" + "=" * 60)
    print("TODOS OS TESTES DO PHONEXTRACT PASSARAM COM SUCESSO!")
    print("=" * 60)

if __name__ == "__main__":
    test_phonextract_scenarios()

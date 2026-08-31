from langchain_core.tools import tool
import paho.mqtt.publish as publish
import json

try:
    from api.logger import mqtt_logger
except ImportError:
    from logger import mqtt_logger

# Armazena as ações executadas durante o ciclo do agente
_current_actions_executed = []
_current_rooms_state = {}
_current_broker_config = {"broker": "test.mosquitto.org", "port": 1883}

def set_execution_context(rooms_state: dict, broker_config: dict):
    """Atualiza o contexto de execução com os cômodos e broker da requisição atual."""
    global _current_actions_executed, _current_rooms_state, _current_broker_config
    _current_actions_executed = []
    _current_rooms_state = rooms_state or {}
    _current_broker_config = broker_config or {"broker": "test.mosquitto.org", "port": 1883}

def get_executed_actions() -> list:
    """Retorna as ações que o agente decidiu executar durante o processamento."""
    return list(_current_actions_executed)

@tool
def controlar_luzes(topico_ou_nome_comodo: str, acao: str) -> str:
    """
    Liga ou desliga a luz de um cômodo específico da residência.
    
    Args:
        topico_ou_nome_comodo: O nome ou o tópico do cômodo (ex: 'sala', 'quarto', 'cozinha', 'quarto 1').
        acao: O estado desejado, 'ON' para ligar/acender ou 'OFF' para desligar/apagar.
    """
    acao_upper = acao.strip().upper()
    if acao_upper not in ["ON", "OFF"]:
        if "LIG" in acao_upper or "ACEND" in acao_upper:
            acao_upper = "ON"
        else:
            acao_upper = "OFF"
            
    slug = (
        topico_ou_nome_comodo.lower()
        .replace(" ", "")
        .replace("-", "")
        .replace("quarto1", "quarto1")
    )
    
    # Registra ação para retorno na API
    _current_actions_executed.append({
        "topic": slug,
        "state": acao_upper
    })
    
    # Atualiza estado em memória
    _current_rooms_state[slug] = (acao_upper == "ON")
    
    mqtt_logger.info(f"Comando de luz: Cômodo='{topico_ou_nome_comodo}' (slug='{slug}'), Ação='{acao_upper}'")
    
    # Publica no broker MQTT se configurado
    try:
        broker = _current_broker_config.get("broker", "test.mosquitto.org")
        port = int(_current_broker_config.get("port", 1883))
        publish.single(
            f"pensador/casa/{slug}/set",
            payload=acao_upper,
            hostname=broker,
            port=port,
            keepalive=5
        )
        mqtt_logger.info(f"MQTT Publish Sucesso: pensador/casa/{slug}/set -> {acao_upper} (Broker: {broker}:{port})")
    except Exception as e:
        mqtt_logger.warning(f"Falha ao enviar MQTT via paho-mqtt: {e}")
        
    status_texto = "ligada" if acao_upper == "ON" else "desligada"
    return f"Sucesso: A luz de '{topico_ou_nome_comodo}' foi {status_texto}."

@tool
def relatorio_status_casa() -> str:
    """
    Consulta e retorna o relatório em tempo real do estado de todas as luzes da residência.
    Informa quantas luzes estão acesas, quais cômodos estão ligados e quais estão desligados.
    """
    mqtt_logger.info("Consulta de relatório de status da residência solicitada.")
    if not _current_rooms_state:
        msg = "Resumo da residência: Todas as luzes estão desligadas no momento."
        mqtt_logger.info(msg)
        return msg
        
    acesos = [comodo for comodo, estado in _current_rooms_state.items() if estado]
    apagados = [comodo for comodo, estado in _current_rooms_state.items() if not estado]
    
    total = len(_current_rooms_state)
    total_acesos = len(acesos)
    
    if total_acesos == 0:
        res = f"Relatório da residência: Todas as {total} luzes da casa estão totalmente desligadas."
    elif total_acesos == total:
        res = f"Relatório da residência: Todas as {total} luzes da casa estão acesas: {', '.join(acesos)}."
    else:
        res = (
            f"Relatório da residência: Existem {total_acesos} luz(es) acesa(s) ({', '.join(acesos)}) "
            f"e {len(apagados)} luz(es) apagada(s) ({', '.join(apagados)})."
        )
    mqtt_logger.info(f"Resultado do relatório: {res}")
    return res

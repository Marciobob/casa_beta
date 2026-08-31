import os
from typing import Optional, Dict, Any, List
from langchain_core.tools import tool

try:
    from api.logger import agent_logger
except ImportError:
    from logger import agent_logger


# =========================================================================
# MANUAL COMPLETO E BASE DE CONHECIMENTO DO SISTEMA SMART HOME & AGENTE IA
# =========================================================================

MANUAL_SECTIONS: Dict[str, Dict[str, Any]] = {
    "visao_geral": {
        "titulo": "🏠 Visão Geral do Sistema Smart Home & Agente Sexta-Feira",
        "palavras_chave": ["geral", "sistema", "visao", "como funciona", "inicio", "painel", "dashboard", "oque e"],
        "resumo": "Plataforma completa de casa inteligente integrada a um Agente IA de voz, automações em segundo plano, visão computacional e serviços Google.",
        "conteudo": """
O sistema Smart Home é uma plataforma residencial autônoma que une automação IoT (MQTT), inteligência artificial conversacional com voz (Sexta-Feira), visão computacional com reconhecimento facial e integração total com serviços do Google e Telegram.

Principais Recursos:
1. Agente Inteligente com Voz (TTS Neural e Escuta Contínua com Wake Word 'Sexta-Feira').
2. Reconhecimento Facial Inteligente na Câmera com Pré-Filtro local OpenCV (economiza tokens) e acionamento residencial automático.
3. Automações em Segundo Plano (Resumos no Telegram, Lembretes de Agenda, Rotinas de Luzes e Comandos Periódicos).
4. Integrações Google (Gmail, Google Agenda, Google Tarefas, Google Keep / Listas de Compras e Google Contatos).
5. Bot do Telegram Bidirecional (Notificações com fotos em tempo real e conversa por voz/texto).
6. Controle Residencial MQTT (Acionamento de lâmpadas por cômodo em tempo real).
"""
    },
    "reconhecimento_facial": {
        "titulo": "📹 Reconhecimento Facial, Visão Computacional & Automações de Vídeo",
        "palavras_chave": ["facial", "reconhecimento", "camera", "video", "rosto", "morador", "intruso", "visitante", "presenca", "opencv", "yunet", "tokens"],
        "resumo": "Monitoramento em tempo real com câmera local ou IP RTSP, reconhecimento de moradores cadastrados e alertas com foto no Telegram.",
        "conteudo": """
O módulo de Reconhecimento Facial e Visão Computacional permite que o sistema monitore a residência e tome ações automáticas ao identificar moradores ou visitantes.

Como Funciona:
1. Cadastro de Moradores: Cada morador deve cadastrar sua foto de perfil em 'Meu Perfil' (/profile.html). Essa foto vira a referência biométrica no SQLite.
2. Câmera: Suporta Câmera Local USB (Webcam) ou Câmera IP via stream RTSP (ex: rtsp://admin:senha@192.168.1.100:554/stream1).
3. Pré-Filtro Local OpenCV YuNet: Para economizar 100% dos seus tokens do Gemini, o OpenCV analisa o frame localmente em menos de 5ms. Se o cômodo estiver vazio, a imagem é descartada sem chamar a nuvem. Quando um rosto ou pessoa é detectada, o frame é encaminhado para a IA Vision comparar com os moradores.
4. Acionamento Residencial em Linguagem Natural: Ao criar uma regra de vídeo, você pode escrever comandos livres como 'Acender a luz do quarto 1' ou 'Ligar a luz da sala e da entrada'. Assim que a câmera reconhecer o morador, a IA executa o comando imediatamente.
5. Cooldown Anti-Spam: Intervalo configurável (ex: 30s, 1min, 5min) para evitar disparos repetidos enquanto a pessoa permanece na frente da câmera.
"""
    },
    "automacoes_segundo_plano": {
        "titulo": "⚡ Motor de Automações & Agendamentos em 2º Plano (AutomationEngine)",
        "palavras_chave": ["automacao", "segundo plano", "regras", "agendamento", "automation", "rotina", "tarefas em segundo plano", "engine"],
        "resumo": "Execução contínua de tarefas em segundo plano como resumos diários, lembretes de agenda e monitoramento por vídeo.",
        "conteudo": """
O AutomationEngine roda continuamente no servidor executando tarefas agendadas mesmo com o navegador fechado:

Tipos de Automação Suportados:
1. 📹 Reconhecimento Facial: Monitora a câmera a cada X segundos e aciona luzes/alerta ao reconhecer moradores.
2. 🚨 Alerta de Intruso / Desconhecido: Envia foto e alerta no Telegram caso alguém não cadastrado seja visto.
3. 👥 Detecção de Presença Humana: Detecta qualquer movimento humano na área monitorada.
4. ⏰ Lembrete de Agenda no Telegram: Lê os compromissos da Google Agenda via CalDAV e avisa X minutos antes com deduplicação para não repetir.
5. ☀️ Resumo Matinal Diário: Envia pontualmente (ex: 08:00) a previsão do tempo, compromissos do dia, e-mails não lidos e status da residência no Telegram.
6. 🌙 Resumo Noturno: Envia às 21:00 os afazeres de amanhã e relatório de luzes acesas.
7. 💡 Agendamento de Luzes MQTT: Liga ou desliga luzes em horários fixos.

Controle pelo Agente:
Você pode pedir ao agente de voz ou chat: 'Quais são as minhas automações ativas?', 'Desative a automação meu quarto' ou 'Ative a regra de reconhecimento facial'.
"""
    },
    "telegram": {
        "titulo": "✈️ Integração Telegram Bot (Notificações & Conversa por Voz)",
        "palavras_chave": ["telegram", "bot", "token", "chat id", "botfather", "userinfobot", "notificacao", "alerta"],
        "resumo": "Receba alertas com fotos em tempo real e converse com a Sexta-Feira enviando mensagens de texto ou áudio.",
        "conteudo": """
Como Configurar o Bot do Telegram Passo a Passo:

Passo 1: Criar o Bot
1. Abra o Telegram e pesquise por @BotFather.
2. Envie o comando /newbot.
3. Escolha um nome (ex: Casa Inteligente) e um username terminando em bot (ex: minha_casa_inteligente_bot).
4. O BotFather fornecerá um HTTP API Bot Token (formato: 123456789:ABCdef...). Copie esse token.

Passo 2: Obter o seu Chat ID
1. No Telegram, pesquise por @userinfobot e envie /start.
2. Ele responderá com o seu 'Id' numérico (ex: 8301234492).
3. Inicie uma conversa com o seu próprio bot recém-criado clicando em /start.

Passo 3: Salvar no Sistema
1. Abra 'Configurações' -> 'Integração Telegram'.
2. Cole o Bot Token e o Chat ID e marque 'Ativar Notificações'.
3. Clique em '🧪 Enviar Mensagem de Teste' para validar.

O que o Bot faz:
- Recebe fotos instantâneas ao reconhecer moradores ou visitantes.
- Recebe resumos matinais diários e lembretes de reuniões.
- Permite conversar com a IA Sexta-Feira por texto ou áudios de voz pelo Telegram de qualquer lugar do mundo.
"""
    },
    "google": {
        "titulo": "🌐 Integrações Google (Gmail, Agenda, Tarefas, Keep & Contatos)",
        "palavras_chave": ["google", "gmail", "agenda", "calendar", "tarefas", "tasks", "keep", "notas", "contatos", "senha de app", "caldav", "imap"],
        "resumo": "Sincronização com serviços Google usando protocolo seguro CalDAV, IMAP e Senha de Aplicativo de 16 letras.",
        "conteudo": """
Como Configurar a Integração Google Passo a Passo:

Passo 1: Gerar a Senha de Aplicativo (App Password)
1. Acesse sua Conta Google em: https://myaccount.google.com/
2. Vá em 'Segurança' e certifique-se de que a 'Verificação em 2 etapas' está ATIVADA.
3. Acesse a página de Senhas de App: https://myaccount.google.com/apppasswords
4. Crie uma nova senha com o nome 'SmartHome' ou 'Casa'.
5. O Google gerará uma senha de 16 letras (ex: 'abcd efgh ijkl mnop'). Copie essa senha.

Passo 2: Salvar no Sistema
1. Acesse o Dashboard do Agente ou a tela de Configurações.
2. Insira seu endereço de Gmail (ex: seuemail@gmail.com) e cole a Senha de App de 16 letras.
3. Clique em 'Salvar Credenciais'.

Ferramentas Disponíveis após a Configuração:
- 📅 Google Agenda: Visualização, agendamento de consultas/reuniões e cancelamento.
- ✉️ Gmail: Leitura de novos e-mails, busca por remetente, envio e respostas automáticas.
- ✅ Google Tarefas: Criação de afazeres com prazos, prioridades e conclusão.
- 📝 Google Keep: Criação de notas e listas de compras inteligentes (adicionar produtos, riscar itens comprados).
- 📇 Google Contatos: Busca de telefones e e-mails de amigos e clientes.
"""
    },
    "mqtt_iluminacao": {
        "titulo": "💡 Automação Residencial & Iluminação MQTT",
        "palavras_chave": ["mqtt", "luzes", "lampadas", "comodos", "broker", "rele", "quarto", "sala", "cozinha", "garagem"],
        "resumo": "Controle de relés e iluminação por cômodos via protocolo MQTT de baixa latência.",
        "conteudo": """
Como Funciona o Controle de Luzes:
- Protocolo: MQTT (Message Queuing Telemetry Transport) através do broker configurado (padrão: test.mosquitto.org:1883).
- Tópicos padrão: pensador/casa/{comodo}/set (Payload: 'ON' ou 'OFF').
- Tópico de status: pensador/casa/{comodo}/state.

Como Acionar:
1. Pelo Painel Web: Clique nos cards de cada cômodo para ligar/desligar.
2. Por Voz: Diga 'Sexta-Feira, acenda a luz do quarto' ou 'Apague todas as luzes da casa'.
3. Por Automação de Câmera: Acione luzes automaticamente quando a câmera reconhecer seu rosto ao chegar em casa.
"""
    },
    "ia_voz_wake_word": {
        "titulo": "🎙️ Configurações de IA, Vozes Neurais (TTS) e Wake Word 'Sexta-Feira'",
        "palavras_chave": ["ia", "voz", "tts", "wake word", "escuta continua", "ouvir sempre", "gemini", "openai", "chave api", "modelo"],
        "resumo": "Escolha entre Google Gemini e OpenAI, selecione vozes neurais realistas e use escuta contínua hands-free.",
        "conteudo": """
Configurações do Agente de Voz:

1. Chave de API:
   - Google Gemini: Obtenha gratuitamente em https://aistudio.google.com/
   - OpenAI: Obtenha em https://platform.openai.com/
   - Modelos recomendados: 'gemini-2.5-flash-lite' (ultra-rápido e econômico) ou 'gpt-4o-mini'.

2. Vozes Neurais Realistas (Edge TTS):
   - Vozes masculinas: 'pt-BR-AntonioNeural' e 'pt-BR-FabioNeural'.
   - Vozes femininas: 'pt-BR-FranciscaNeural' e 'pt-BR-ThalitaMultilingualNeural'.
   - A voz selecionada fica salva no SQLite no seu perfil de usuário.

3. Modo 'Ouvir Sempre' (Wake Word):
   - Ative o botão '🎙️ Ouvir Sempre: Ativo' no topo da tela.
   - O microfone fica em espera silenciosa. Basta falar 'Sexta-Feira' seguido do seu pedido para acionar sem precisar tocar na tela.
"""
    },
    "perfil_moradores": {
        "titulo": "👤 Perfil do Usuário & Cadastro de Moradores",
        "palavras_chave": ["perfil", "moradores", "foto", "dados", "biometria", "tipo sanguineo", "preferencias"],
        "resumo": "Cadastro de dados pessoais e fotos de referência facial para cada morador da residência.",
        "conteudo": """
Como Usar a Tela de Perfil (/profile.html):
1. Foto de Referência: Tire uma foto ou faça upload de um retrato nítido do seu rosto. Essa foto é usada pelo OpenCV YuNet e pelo Gemini Vision para reconhecer você na câmera.
2. Memória Pessoal do Agente: Preencha suas preferências, comidas favoritas, alergias, tipo sanguíneo, filmes, notas pessoais e rotinas.
3. Respostas Personalizadas: O agente 'Sexta-Feira' consulta seu perfil para dar respostas contextualizadas e lembrar de preferências familiares.
"""
    }
}


def buscar_no_manual(termo_ou_duvida: str = "") -> str:
    """Busca tópicos e explicações detalhadas na base de conhecimento do sistema."""
    query = (termo_ou_duvida or "").strip().lower()
    if not query or query in ["ajuda", "manual", "tudo", "como funciona", "sistema", "todos"]:
        # Retorna índice completo resumido
        linhas = ["📚 **MANUAL E GUIA DO SISTEMA SMART HOME**\n"]
        for chave, sec in MANUAL_SECTIONS.items():
            linhas.append(f"• **{sec['titulo']}**\n  _{sec['resumo']}_\n")
        linhas.append("\nPara detalhes de um módulo específico, pergunte sobre: Reconhecimento Facial, Automações de Vídeo, Telegram, Google/Gmail, Luzes MQTT, Voz/IA ou Perfil.")
        return "\n".join(linhas)

    # Busca por correspondência nas palavras-chave e títulos
    resultados = []
    for chave, sec in MANUAL_SECTIONS.items():
        score = 0
        if query in chave or chave in query:
            score += 10
        if query in sec["titulo"].lower():
            score += 8
        for kw in sec["palavras_chave"]:
            if kw in query or query in kw:
                score += 5
        if query in sec["conteudo"].lower():
            score += 2

        if score > 0:
            resultados.append((score, sec))

    resultados.sort(key=lambda x: x[0], reverse=True)

    if not resultados:
        return (
            f"Não encontrei um tópico exato sobre '{termo_ou_duvida}'. "
            "Você pode perguntar sobre: Reconhecimento Facial, Automações em Segundo Plano, Telegram, "
            "Configuração Google/Gmail, Luzes MQTT, Voz/Wake Word ou Perfil de Moradores."
        )

    # Retorna as seções mais relevantes
    melhores = [r[1] for r in resultados[:2]]
    resp = []
    for m in melhores:
        resp.append(f"### {m['titulo']}\n{m['conteudo'].strip()}")

    return "\n\n".join(resp)


# =========================================================================
# FERRAMENTA LANGCHAIN DE CONSULTA AO MANUAL DO SISTEMA
# =========================================================================

@tool
def consultar_manual_sistema(modulo_ou_duvida: str = "visao_geral") -> str:
    """
    Consulta o manual oficial e a documentação completa de todas as telas, funcionalidades e configurações do sistema Smart Home.
    Use sempre que o usuário perguntar como configurar algo, como funciona uma tela ou ferramenta, como gerar senhas de app do Google,
    como criar o bot do Telegram com o BotFather, como funciona o reconhecimento facial, como funcionam as automações de vídeo,
    como funciona o pré-filtro OpenCV para economizar tokens, ou tiver qualquer dúvida de uso do sistema.
    
    Args:
        modulo_ou_duvida: O tema, tela ou dúvida do usuário (ex: "reconhecimento facial", "telegram", "google", "automacoes", "luzes mqtt", "como configurar").
    """
    agent_logger.info(f"[ManualTools] Consulta ao manual solicitada: '{modulo_ou_duvida}'")
    conteudo = buscar_no_manual(modulo_ou_duvida)
    return conteudo

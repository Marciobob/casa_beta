# 🏠 Casa Beta - Smart Home AI Agent 🤖

> Plataforma completa de **Casa Inteligente e Assistente Pessoal com Inteligência Artificial**, equipada com agente conversacional por voz contínua, memória de longo prazo e aprendizado autônomo, contexto temporal em tempo real, controle da máquina física (volume, brilho, navegador), player de música nos alto-falantes, automações residenciais IoT (MQTT), visão computacional com reconhecimento facial, integração com serviços Google e Telegram, e pesquisa com transcrição de tutoriais do YouTube.

---

## 📋 Sumário
1. [Visão Geral & Arquitetura](#-visão-geral--arquitetura)
2. [Principais Recursos](#-principais-recursos)
3. [Ferramentas Integradas do Agente](#-ferramentas-integradas-do-agente)
4. [Tecnologias Utilizadas](#-tecnologias-utilizadas)
5. [Estrutura do Projeto](#-estrutura-do-projeto)
6. [Instalação e Execução Local](#-instalação-e-execução-local)
7. [Deploy em Servidor VPS (Produção)](#-deploy-em-servidor-vps-produção)
8. [Configuração de Variáveis de Ambiente (.env)](#-configuração-de-variáveis-de-ambiente-env)
9. [Rotas e Telas do Sistema](#-rotas-e-telas-do-sistema)

---

## 🌟 Visão Geral & Arquitetura

O **Casa Beta** é uma solução inteligente e modular desenvolvida sobre **FastAPI**, **LangChain** e **SQLite**. O sistema integra um painel de controle 3D em tempo real com um agente de inteligência artificial multilíngue com voz neural natural, capaz de executar ações no mundo real, interagir com a máquina local e gerenciar a rotina do usuário.

```
                     ┌────────────────────────────────────────┐
                     │   Interfaces Web (Dashboard / 3D)      │
                     │  - index.html (Terminal do Agente)     │
                     │  - casa.html (Controle 3D dos Cômodos) │
                     │  - profile.html (Cadastro Facial)      │
                     │  - config.html (Central Configurações) │
                     └───────────────────┬────────────────────┘
                                         │ WebSocket / REST API
                                         ▼
                     ┌────────────────────────────────────────┐
                     │      FastAPI Backend (Porta 8000)      │
                     │  - Autenticação JWT + Bcrypt           │
                     │  - SQLite Multi-usuário                │
                     │  - Motor de Automações em Background   │
                     │  - Edge-TTS (Voz Neural com Cache)     │
                     └───────────────────┬────────────────────┘
                                         │
                 ┌───────────────────────┼───────────────────────┐
                 ▼                       ▼                       ▼
      ┌────────────────────┐  ┌────────────────────┐  ┌────────────────────┐
      │  LangChain Agent   │  │   MQTT Broker      │  │  Bot do Telegram   │
      │  (Gemini / OpenAI) │  │  (Luzes & IoT)     │  │  (Alertas & Voz)   │
      └──────────┬─────────┘  └────────────────────┘  └────────────────────┘
                 │
                 ├─► 🧠 Memória de Longo Prazo & Aprendizado Autônomo
                 ├─► 🕒 Contexto Temporal em Tempo Real (Data, Hora, Fuso)
                 ├─► 🎵 Streaming de Música & Alto-Falante (YouTube + ffplay)
                 ├─► 💻 Controle da Máquina Física (Volume, Brilho, Navegador)
                 ├─► 📺 YouTube (Pesquisa & Transcrição de Vídeos)
                 ├─► 🌐 DuckDuckGo (Pesquisa Web em Tempo Real)
                 ├─► ✉️ Gmail (IMAP / SMTP SSL)
                 ├─► 📅 Google Agenda (CalDAV)
                 ├─► 👤 Google Contatos (CardDAV)
                 ├─► ✅ Google Tarefas & Lembretes
                 ├─► 📝 Google Keep / Listas de Compras
                 ├─► 📷 Visão Computacional (OpenCV YuNet + Multimodal)
                 └─► 👤 Perfil do Morador
```

---

## ✨ Principais Recursos

- **🧠 Memória de Longo Prazo & Aprendizado Autônomo**:
  - A IA identifica e grava proativamente novos gostos, preferências, rotinas e instruções compartilhados em conversas diárias.
  - Injeção dinâmica das memórias mais relevantes e importantes no System Prompt de cada diálogo.
  - Ferramentas completas para consultar, listar e esquecer memórias sob demanda.
- **🕒 Contexto Temporal Preciso em Tempo Real**:
  - Injeção automática da data por extenso em português, dia da semana, hora com segundos e fuso horário a cada comando.
  - Respostas precisas para *"que horas são?"*, *"o que tenho amanhã?"*, agendamentos e saudações conforme o turno.
- **🎵 Música, Podcasts & Player nos Alto-falantes**:
  - Busca e reprodução contínua de músicas, bandas, gêneros e podcasts diretamente nos alto-falantes em segundo plano com `yt-dlp` e `ffplay`.
- **💻 Controle da Máquina Física & Hardware**:
  - Controle nativo do volume do computador (aumentar, abaixar, mutar, porcentagem), brilho da tela e abertura segura de abas/sites no navegador, com trava de segurança configurável.
- **🎙️ Voz Neural & Escuta Contínua**:
  - Escuta contínua com ativação por Wake Word (*"Sexta-Feira"*, configurável) e watchdog automático anti-interrupção.
  - Síntese de voz neural ultra-rápida (Edge TTS) com feedback instantâneo sem silêncio (*"Tô pesquisando..."*, *"Tô vendo isso agora..."*).
- **📺 YouTube & Tutoriais com Transcrição**:
  - Busca tutoriais em vídeo, extrai automaticamente as legendas/transcrições em português e resume o passo a passo estruturado.
- **📷 Reconhecimento Facial Inteligente**:
  - Pré-filtro facial local com OpenCV (economiza tokens de IA) e identificação de moradores cadastrados para saudações personalizadas.
- **💡 Automação Residencial MQTT**:
  - Controle de iluminação e status em tempo real por cômodo via broker MQTT.
- **📬 Produtividade Google Integrada**:
  - E-mails (Gmail), Compromissos (Calendar), Contatos, Tarefas e Listas de Compras (Keep).
- **🤖 Bot do Telegram Bidirecional**:
  - Recebe comandos por texto e voz, envia fotos da câmera e notificações de automações.
- **⚙️ Motor de Automações em Segundo Plano**:
  - Regras agendadas de agenda, lembretes, rotinas de iluminação e alertas de movimento.

---

## 🛠️ Ferramentas Integradas do Agente

| Ferramenta | Descrição |
|---|---|
| `gravar_memoria_longo_prazo` | Grava autonomamente preferências, hábitos, gostos e regras do usuário no SQLite. |
| `consultar_memorias_longo_prazo` | Pesquisa na base de memórias consolidadas por termos ou categorias. |
| `listar_todas_memorias` | Lista tudo o que o assistente sabe e lembra sobre o usuário. |
| `esquecer_memoria` | Exclui memórias obsoletas ou a pedido do morador. |
| `tocar_musica` | Busca e inicia reprodução de áudio de músicas, artistas e podcasts no YouTube em segundo plano. |
| `parar_musica` | Interrompe e silencia a reprodução da música no alto-falante. |
| `status_musica` | Informa qual música/áudio está tocando no momento. |
| `controlar_volume_sistema` | Ajusta o volume do som do computador (porcentagem, aumento, diminuição, mudo). |
| `controlar_brilho_tela` | Ajusta o brilho da tela/monitores físicos. |
| `abrir_navegador_sistema` | Abre páginas web, vídeos ou buscas no navegador padrão da máquina. |
| `fechar_navegador_sistema` | Fecha abas/páginas abertas pelo assistente (com proteção do painel principal). |
| `pesquisar_e_transcrever_youtube` | Pesquisa tutoriais e vídeos no YouTube, extrai a transcrição das falas e sintetiza o passo a passo. |
| `pesquisar_na_internet` | Realiza buscas em tempo real na web (previsão do tempo, notícias, fatos, curiosidades). |
| `controlar_luzes` | Liga (`ON`) ou desliga (`OFF`) iluminação dos cômodos via protocolo MQTT. |
| `relatorio_status_casa` | Consulta o estado de iluminação de todos os cômodos da residência. |
| `ler_emails_recentes` / `buscar_emails` / `enviar_email` / `responder_email` / `apagar_email` | Gerencia e-mails completos do Gmail via protocolo seguro IMAP/SMTP. |
| `listar_compromissos` / `agendar_compromisso` / `buscar_compromissos` / `cancelar_compromisso` | Consulta e gerencia a agenda do Google Calendar. |
| `buscar_contato` / `salvar_contato` / `listar_contatos` / `excluir_contato` | Consulta e sincroniza a agenda de contatos. |
| `criar_tarefa` / `listar_tarefas` / `concluir_tarefa` / `excluir_tarefa` / `buscar_tarefas` | Gerenciamento completo de to-do list e tarefas. |
| `criar_nota` / `adicionar_itens_lista` / `marcar_item_lista` / `ler_nota` / `listar_notas` | Gerenciamento de notas livres e listas de compras com checkboxes. |
| `ver_camera` / `detectar_e_cumprimentar_pessoas` / `identificar_morador_ou_visitante` | Análise de visão computacional da câmera ao vivo. |
| `enviar_mensagem_telegram` / `enviar_foto_telegram` | Notificações externas via bot do Telegram. |
| `listar_automacoes` / `controlar_automacao` / `criar_automacao` / `excluir_automacao` | Gerencia regras de execução automática em background. |
| `consultar_perfil_usuario` | Consulta dados biográficos e médicos do morador. |
| `consultar_manual_sistema` | Base de conhecimento e manual de instrução do sistema. |

---

## 💻 Tecnologias Utilizadas

- **Backend**: Python 3.10+, FastAPI, Uvicorn, Pydantic, Python-Jose (JWT), Passlib/Bcrypt.
- **IA & LLM**: LangChain, Google Generative AI (`gemini-2.5-flash-lite`), OpenAI (`gpt-4o-mini`).
- **Áudio & Vídeo**: `edge-tts` (Microsoft Neural Voices), `yt-dlp`, `ffplay` (FFmpeg), `youtube-transcript-api`, OpenCV (`cv2`).
- **Protocolos & IoT**: Paho-MQTT, CalDAV, IMAP4/SMTP SSL.
- **Frontend**: HTML5, Tailwind CSS, JavaScript Vanilla ES6+, Three.js (Painel 3D), Web Speech API.
- **Banco de Dados**: SQLite com isolamento relacional por usuário (`smarthome.db`).

---

## 📂 Estrutura do Projeto

```
casa_beta/api/
├── main.py                  # Ponto de entrada FastAPI e rotas REST
├── agent.py                 # Orquestração do agente LangChain, prompt e contexto temporal
├── auth.py                  # Autenticação JWT, login, registro e segurança
├── database.py              # Camada de banco de dados SQLite (CRUD, memórias, perfis)
├── automation_engine.py     # Motor de execução de regras em background
├── video_automation.py      # Automação de processamento contínuo de vídeo
├── telegram_bot.py          # Gerenciador de bots do Telegram por usuário
├── logger.py                # Sistema de logging estruturado
├── requirements.txt         # Dependências do ecossistema Python
├── .env.example             # Modelo de variáveis de ambiente
├── smarthome.db             # Banco de dados local SQLite
├── static/                  # Interfaces web e assets
│   ├── index.html           # Painel Principal e Terminal do Agente
│   ├── casa.html            # Dashboard 3D da Casa Inteligente
│   ├── login.html           # Tela de autenticação e registro
│   ├── profile.html         # Gestão de Moradores e Reconhecimento Facial
│   ├── config/              # Central Unificada de Configurações
│   │   └── config.html      # Tela de configurações com permissões de sistema
│   └── guide_modal.js       # Guia visual interativo do sistema
└── tools/                   # Ferramentas modulares do Agente LangChain
    ├── memory_tools.py      # Memória de longo prazo e aprendizado contínuo
    ├── music_tools.py       # Player de áudio e streaming nos alto-falantes
    ├── system_tools.py      # Controle de volume, brilho e navegador do sistema
    ├── youtube_tools.py     # Busca e transcrição de vídeos do YouTube
    ├── search_tools.py      # Busca na internet (DuckDuckGo)
    ├── mqtt_tools.py        # Acionamento de luzes MQTT
    ├── vision_tools.py      # Reconhecimento facial e captura de câmera
    ├── gmail_tools.py       # Integração com Gmail
    ├── calendar_tools.py    # Integração com Google Agenda
    ├── contact_tools.py     # Integração com Google Contatos
    ├── task_tools.py        # Integração com Google Tarefas
    ├── keep_tools.py        # Integração com Google Keep / Listas
    ├── telegram_tools.py    # Disparo de mensagens no Telegram
    ├── automation_tools.py  # Controle de regras de automação
    ├── profile_tools.py     # Memória de perfil do usuário
    └── manual_tools.py      # Manual do usuário integrado
```

---

## 🚀 Instalação e Execução Local

### 1. Pré-requisitos
- **Python 3.10** ou superior instalado (ou ambiente Conda).
- **Git** instalado.

### 2. Clonar o Repositório e Criar Ambiente Virtual

```bash
# Clone o repositório
git clone https://github.com/Marciobob/casa_beta.git
cd casa_beta/api

# Opção A: Usando Python venv padrão
python3 -m venv venv
source venv/bin/activate  # Linux/macOS
# No Windows: venv\Scripts\activate

# Opção B: Usando Conda
conda create -n agente_api python=3.10 -y
conda activate agente_api
```

### 3. Instalar Dependências

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configurar Variáveis de Ambiente

Crie o arquivo `.env` a partir do exemplo:

```bash
cp .env.example .env
```

Edite o `.env` caso queira definir chaves padrão de LLM ou segredo JWT:
```ini
JWT_SECRET_KEY=smart_home_secret_key_2026_jwt_token_secure_98412
# As chaves de API do Gemini/OpenAI e credenciais Google também podem ser inseridas diretamente pela tela de configurações do painel web.
```

### 5. Executar o Servidor

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Acesse no navegador:
- **Painel Geral & Terminal**: [http://localhost:8000/](http://localhost:8000/)
- **Dashboard 3D dos Cômodos**: [http://localhost:8000/casa.html](http://localhost:8000/casa.html)
- **Perfil & Reconhecimento Facial**: [http://localhost:8000/profile.html](http://localhost:8000/profile.html)
- **Documentação Swagger da API**: [http://localhost:8000/docs](http://localhost:8000/docs)

---

## 🌐 Deploy em Servidor VPS (Produção)

Guia completo para implantação em servidores Linux (Ubuntu 22.04 / 24.04 LTS ou Debian).

### Passo 1: Atualizar o Sistema e Instalar Pacotes Básicos

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip python3-venv git nginx certbot python3-certbot-nginx libgl1 libglib2.0-0 ffmpeg
```

### Passo 2: Clonar o Projeto e Configurar Ambiente

```bash
# Clone na pasta de sua preferência (ex: /var/www ou /home/usuario)
cd /var/www
sudo git clone https://github.com/Marciobob/casa_beta.git
sudo chown -R $USER:$USER /var/www/casa_beta
cd /var/www/casa_beta/api

# Cria e ativa o ambiente virtual
python3 -m venv venv
source venv/bin/activate

# Instala dependências
pip install --upgrade pip
pip install -r requirements.txt

# Configura o .env
cp .env.example .env
```

### Passo 3: Configurar Serviço Systemd (Execução Contínua em Background)

Crie o arquivo de serviço do Systemd para manter a API rodando automaticamente:

```bash
sudo nano /etc/systemd/system/casabeta.service
```

Cole a seguinte configuração (ajuste os caminhos e usuário caso necessário):

```ini
[Unit]
Description=Casa Beta Smart Home AI Agent API
After=network.target

[Service]
User=root
WorkingDirectory=/var/www/casa_beta/api
Environment="PATH=/var/www/casa_beta/api/venv/bin"
ExecStart=/var/www/casa_beta/api/venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000 --workers 2

Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Ative e inicie o serviço:

```bash
sudo systemctl daemon-reload
sudo systemctl enable casabeta
sudo systemctl start casabeta
sudo systemctl status casabeta
```

### Passo 4: Configurar Nginx como Reverse Proxy

Crie a configuração do site no Nginx:

```bash
sudo nano /etc/nginx/sites-available/casabeta
```

Adicione a configuração (substitua `seu-dominio.com.br` pelo seu domínio ou IP da VPS):

```nginx
server {
    server_name seu-dominio.com.br;

    client_max_body_size 50M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Suporte a WebSockets e Streaming de Áudio/Vídeo
        proxy_read_timeout 86400s;
        proxy_send_timeout 86400s;
    }
}
```

Ative o site e reinicie o Nginx:

```bash
sudo ln -s /etc/nginx/sites-available/casabeta /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### Passo 5: Gerar Certificado SSL Gratuito (HTTPS) com Let's Encrypt

> **Nota**: Para o microfone e voz funcionarem sem bloqueios de segurança do navegador em conexões remotas, o uso de HTTPS é obrigatório pelo padrão WebRTC/Web Speech API.

```bash
sudo certbot --nginx -d seu-dominio.com.br
```

Siga as instruções na tela e escolha a opção para redirecionar HTTP para HTTPS automaticamente.

---

## 🔒 Configuração de Variáveis de Ambiente (.env)

| Variável | Obrigatória? | Descrição |
|---|---|---|
| `JWT_SECRET_KEY` | Sim | Chave secreta para criptografia e validação de tokens JWT de login. |
| `GEMINI_API_KEY` | Opcional | Chave da API Google Gemini (pode ser informada via tela de configurações). |
| `OPENAI_API_KEY` | Opcional | Chave da API OpenAI (pode ser informada via tela de configurações). |
| `GMAIL_EMAIL` | Opcional | E-mail da conta Google para integração com Gmail / Calendar / Keep. |
| `GMAIL_APP_PASSWORD` | Opcional | Senha de aplicativo de 16 dígitos gerada em `myaccount.google.com/apppasswords`. |

---

## 📱 Rotas e Telas do Sistema

- **`/` ou `/agent`**: Terminal do Agente conversacional por voz contínua, histórico de mensagens, console de depuração e atalhos de ferramentas.
- **`/casa.html`**: Painel 3D interativo para acionamento de lâmpadas MQTT, status dos cômodos e controle por voz do ambiente.
- **`/profile.html`**: Cadastro de fotos de moradores para reconhecimento facial e personalização de perfil.
- **`/login.html`**: Tela de autenticação JWT e registro de novos usuários.
- **`/docs`**: Documentação interativa de todos os endpoints REST (FastAPI / Swagger UI).

---

## 📄 Licença e Suporte

Desenvolvido por **Marcio** para controle residencial autônomo e assistência pessoal com IA.
Distribuído sob licença proprietária/MIT para fins de automação pessoal e profissional.

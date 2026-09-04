/**
 * guide_modal.js - Sistema Centralizado de Guias, Tutoriais e Informações das Ferramentas
 * Permite ao usuário entender e configurar passo a passo cada tela e ferramenta da plataforma.
 */

const SYSTEM_GUIDES = {
    visao_geral: {
        icone: "🏠",
        titulo: "Visão Geral & Central do Agente",
        categoria: "Dashboard Principal",
        resumo: "Central unificada com assistente de voz inteligente (Sexta-Feira), controle residencial e integrações Google/Telegram.",
        passo_a_passo: [
            "Converse com a <b>Sexta-Feira</b> via texto no terminal ou clicando em <b>🎙️ Falar por Voz</b>.",
            "Para controle 100% sem as mãos, ative o botão <b>🎙️ Ouvir Sempre</b> no topo da tela e diga <i>'Sexta-Feira'</i> antes de qualquer pedido.",
            "Acesse o <b>Dashboard da Casa</b> para ver as luzes e cômodos ou <b>Automações</b> para gerenciar regras de fundo.",
            "Configure suas credenciais Google (Gmail, Agenda, Tarefas) e chave de API para liberar todo o poder do agente."
        ],
        exemplos_comandos: [
            "Sexta-Feira, quais são as novidades e meus compromissos de hoje?",
            "Ligue a luz do quarto e verifique meus e-mails não lidos",
            "O que tem na minha lista de compras?",
            "Pesquise as principais notícias do dia no Brasil"
        ],
        dicas: "Você pode usar o microfone em qualquer tela ou conversar diretamente pelo aplicativo do Telegram com o mesmo assistente."
    },

    reconhecimento_facial: {
        icone: "📹",
        titulo: "Reconhecimento Facial & Visão Computacional",
        categoria: "Câmera & Segurança",
        resumo: "Monitoramento inteligente com identificação de moradores cadastrados, alertas de visitante no Telegram e acionamento residencial automático.",
        passo_a_passo: [
            "<b>1. Cadastre sua foto oficial:</b> Acesse <a href='/profile.html' class='text-indigo-400 underline font-bold'>Meu Perfil</a> e envie uma foto nítida do seu rosto ou tire com a câmera.",
            "<b>2. Configure a Câmera:</b> No menu Configurações, escolha entre a Câmera Local (Webcam USB) ou Câmera IP (RTSP).",
            "<b>3. Crie uma Regra de Vídeo:</b> No modal de Automações, crie uma regra como <i>'Reconhecer Morador'</i>.",
            "<b>4. Comando Residencial Livre:</b> No campo de acionamento, digite livremente o que a IA deve fazer ao te ver (ex: <i>'Acender a luz do quarto 1'</i>).",
            "<b>5. Economia de Tokens (OpenCV):</b> O sistema possui um pré-filtro neural local OpenCV YuNet que só consome tokens do Gemini quando detectar uma pessoa real no cômodo!"
        ],
        exemplos_comandos: [
            "Sexta-Feira, olhe a câmera e descreva o que está vendo",
            "Verifique se tem alguém na sala e cumprimente quem estiver",
            "Quem está na câmera é um morador cadastrado ou visitante?",
            "Me envie uma foto da câmera agora no Telegram"
        ],
        dicas: "O Cooldown padrão de 5 minutos evita que a IA fique disparando alertas repetitivos enquanto você estiver sentado na frente da câmera."
    },

    automacoes: {
        icone: "⚡",
        titulo: "Motor de Automações em Segundo Plano",
        categoria: "Rotinas Autônomas",
        resumo: "Execução contínua de tarefas programadas (mesmo com navegador fechado), como resumos matinais, lembretes de reuniões e regras de câmera.",
        passo_a_passo: [
            "Clique no botão <b>⚡ Automações</b> no topo da tela para abrir o gerenciador.",
            "Escolha entre os modelos prontos (Resumo Matinal, Lembrete de Agenda, Alerta de Intruso) ou crie uma personalizada.",
            "Defina o gatilho (ex: horário diário <i>'08:00'</i>, minutos de antecedência <i>'15'</i> ou intervalo de varredura <i>'30s'</i>).",
            "Para testar imediatamente sem esperar o horário, clique em <b>🧪 Testar Agora</b> no card da automação.",
            "Você também pode gerenciar suas regras por voz dizendo: <i>'Desative a automação meu quarto'</i> ou <i>'Ative a regra do quarto'</i>."
        ],
        exemplos_comandos: [
            "Sexta-Feira, quais são as minhas automações cadastradas?",
            "Desative a regra meu quarto",
            "Ative a automação do quarto novamente",
            "Crie um resumo matinal diário às 08:00 no Telegram"
        ],
        dicas: "Ao clicar em 'Testar Agora', o cooldown é automaticamente zerado para permitir testes instantâneos."
    },

    telegram: {
        icone: "📱",
        titulo: "Integração Telegram Bot",
        categoria: "Notificações & Controle Remoto",
        resumo: "Receba alertas com fotos da câmera em tempo real, resumos matinais e converse com a IA por mensagens de texto ou áudios de voz.",
        passo_a_passo: [
            "<b>1. Crie seu Bot no Telegram:</b> Abra o Telegram, procure pelo contato oficial <b>@BotFather</b> e envie o comando <code>/newbot</code>.",
            "<b>2. Defina Nome e Username:</b> Escolha um nome (ex: <i>Casa Inteligente</i>) e um username terminando em bot (ex: <i>minha_casa_ia_bot</i>).",
            "<b>3. Copie o Bot Token:</b> O BotFather fornecerá um código como <code>123456789:ABCdefGHI...</code>.",
            "<b>4. Obtenha seu Chat ID:</b> Pesquise pelo bot <b>@userinfobot</b> no Telegram e envie qualquer mensagem. Ele responderá com o seu <b>Id numérico</b> (ex: <i>8301234492</i>).",
            "<b>5. Inicie seu Bot:</b> Abra a conversa com o seu próprio bot recém-criado e clique em <b>Iniciar (/start)</b>.",
            "<b>6. Salve no Sistema:</b> Cole o Token e o Chat ID nas Configurações da plataforma e clique em <b>🧪 Testar Conexão</b>."
        ],
        exemplos_comandos: [
            "Sexta-Feira, me envie uma mensagem no Telegram com o resumo da casa",
            "Envie uma foto da câmera agora no meu Telegram",
            "(No Telegram) 'Ligue a luz da sala e da cozinha'",
            "(No Telegram enviando áudio) 'Quais os meus compromissos de hoje?'"
        ],
        dicas: "Você pode enviar áudios de voz pelo Telegram que a Sexta-Feira escuta, transcreve e responde com áudio em português!"
    },

    google: {
        icone: "🌐",
        titulo: "Integração Google (Gmail, Agenda, Tarefas & Keep)",
        categoria: "Serviços em Nuvem",
        resumo: "Acesso unificado aos seus e-mails, compromissos da agenda CalDAV, afazeres To-Do e listas de compras do Keep usando Senha de Aplicativo segura.",
        passo_a_passo: [
            "<b>1. Acesse sua Conta Google:</b> Entre em <a href='https://myaccount.google.com/' target='_blank' class='text-indigo-400 underline font-bold'>myaccount.google.com</a>.",
            "<b>2. Verificação em 2 Etapas:</b> Vá na aba <b>Segurança</b> e confirme que a <i>Verificação em duas etapas</i> está ativada.",
            "<b>3. Gerar Senha de App:</b> Acesse <a href='https://myaccount.google.com/apppasswords' target='_blank' class='text-indigo-400 underline font-bold'>myaccount.google.com/apppasswords</a>.",
            "<b>4. Criar Senha:</b> Dê o nome <i>'SmartHome'</i> e clique em Criar. O Google exibirá uma senha de 16 letras (ex: <i>abcd efgh ijkl mnop</i>).",
            "<b>5. Salvar na Plataforma:</b> No Dashboard ou Configurações, insira seu e-mail do Gmail e cole essa senha de 16 letras."
        ],
        exemplos_comandos: [
            "Verifique meus e-mails não lidos no Gmail",
            "Quais são os meus compromissos na agenda para hoje e amanhã?",
            "Crie uma tarefa para pagar o condomínio na sexta-feira",
            "Adicione café, pão de queijo e leite na lista de compras"
        ],
        dicas: "A Senha de Aplicativo é 100% segura e não expõe sua senha principal da conta Google."
    },

    gmail: {
        icone: "📧",
        titulo: "Gmail & Mensagens",
        categoria: "Comunicação",
        resumo: "Consulte caixas de entrada, leia novos e-mails não lidos, envie mensagens para contatos e responda e-mails com voz.",
        passo_a_passo: [
            "Configure suas credenciais Google (Gmail + Senha de App de 16 letras).",
            "Peça à Sexta-Feira para verificar e-mails recentes ou não lidos.",
            "Para enviar um e-mail, basta dizer o nome do contato ou endereço (ex: <i>'Envie um e-mail para o Pedro avisando que cheguei'</i>)."
        ],
        exemplos_comandos: [
            "Tem algum e-mail importante não lido no meu Gmail?",
            "Quais foram os últimos 3 e-mails recebidos?",
            "Envie um e-mail para contato@exemplo.com com o assunto Reunião",
            "Responda o último e-mail dizendo que confirmo presença"
        ],
        dicas: "A IA busca automaticamente o e-mail na sua agenda de Contatos do Google caso você fale apenas o nome da pessoa."
    },

    calendar: {
        icone: "📅",
        titulo: "Google Agenda & Calendar",
        categoria: "Produtividade & CalDAV",
        resumo: "Sincronização bidirecional de eventos e reuniões via protocolo CalDAV seguro.",
        passo_a_passo: [
            "Com as credenciais Google salvas, o sistema lê seus calendários oficiais.",
            "Consulte eventos por períodos: hoje, amanhã, fim de semana ou próximos 7 dias.",
            "Agende consultas ou reuniões dizendo a data, horário e descrição.",
            "Crie uma regra em <b>⚡ Automações</b> para ser avisado no Telegram 15 minutos antes de cada evento!"
        ],
        exemplos_comandos: [
            "Quais são os meus compromissos para hoje?",
            "Agende uma reunião com a equipe amanhã às 14h",
            "Pesquise quando é a minha próxima consulta médica na agenda",
            "Cancele o compromisso de almoço na quinta-feira"
        ],
        dicas: "Os lembretes de agenda possuem deduplicação inteligente para nunca enviar o mesmo lembrete duas vezes."
    },

    tarefas: {
        icone: "✅",
        titulo: "Google Tarefas & Afazeres (To-Do)",
        categoria: "Organização",
        resumo: "Gerencie listas de afazeres diários com prioridades, datas de entrega e sincronização.",
        passo_a_passo: [
            "Crie afazeres rápidos falando com o agente.",
            "Consulte suas tarefas pendentes, atrasadas ou concluídas a qualquer momento.",
            "Marque tarefas como concluídas por voz dizendo que terminou."
        ],
        exemplos_comandos: [
            "Quais são as minhas tarefas pendentes para hoje?",
            "Crie uma tarefa de alta prioridade para revisar o contrato amanhã",
            "Marque a tarefa de pagar a conta de luz como concluída",
            "Remova a tarefa de comprar lâmpadas da minha lista"
        ],
        dicas: "Tarefas com data de vencimento aparecem destacadas no resumo diário matinal."
    },

    keep: {
        icone: "📝",
        titulo: "Google Keep, Notas & Listas de Compras",
        categoria: "Anotações & Checklists",
        resumo: "Crie notas de texto livre, rascunhos de ideias e listas de compras dinâmicas com itens marcáveis.",
        passo_a_passo: [
            "Peça para criar uma nova nota ou lista de compras.",
            "Adicione novos produtos à lista existente a qualquer momento.",
            "Conforme for comprando no supermercado, diga <i>'Já peguei o leite'</i> para riscar o item."
        ],
        exemplos_comandos: [
            "O que tem na minha lista de compras?",
            "Crie uma lista de compras com café, arroz, feijão e queijo",
            "Adicione manteiga e azeite na lista de compras",
            "Marque o arroz como comprado na lista de compras"
        ],
        dicas: "Você pode ter várias listas separadas, como 'Compras Mercado', 'Farmácia' ou 'Materiais de Construção'."
    },

    mqtt: {
        icone: "💡",
        titulo: "Automação Residencial & Lâmpadas MQTT",
        categoria: "Internet das Coisas (IoT)",
        resumo: "Controle de relés, interruptores e iluminação por cômodos com atualização em tempo real e protocolo MQTT.",
        passo_a_passo: [
            "No <b>Dashboard da Casa</b> (/casa.html), você visualiza todos os cômodos cadastrados.",
            "Clique nos botões dos cards para ligar ou desligar as lâmpadas.",
            "Fale com o agente por voz ou texto para acionar cômodos individuais ou múltiplos.",
            "Vincule o acionamento às regras de Reconhecimento Facial para acender luzes ao chegar!"
        ],
        exemplos_comandos: [
            "Sexta-Feira, acenda a luz do quarto",
            "Apague todas as luzes da casa",
            "Ligue a luz da sala e da garagem",
            "Qual é o relatório das luzes acesas no momento?"
        ],
        dicas: "O tópico padrão MQTT utilizado é <code>pensador/casa/{comodo}/set</code> com payload <code>ON</code> / <code>OFF</code>."
    },

    voz_ia: {
        icone: "🎙️",
        titulo: "Configuração de IA, Vozes Neurais (TTS) & Wake Word",
        categoria: "Inteligência Artificial",
        resumo: "Escolha seu modelo de IA preferido, selecione vozes neurais realistas em português e ative escuta contínua.",
        passo_a_passo: [
            "<b>1. Chave de API:</b> Obtenha sua chave gratuita do Gemini em <a href='https://aistudio.google.com/' target='_blank' class='text-indigo-400 underline font-bold'>Google AI Studio</a> ou na OpenAI.",
            "<b>2. Escolha o Modelo:</b> Recomendamos o <code>gemini-2.5-flash-lite</code> (ultra-rápido, inteligente e de baixíssimo custo).",
            "<b>3. Selecione a Voz:</b> Escolha entre as vozes neurais ultra-realistas (ex: <i>Antonio, Fabio, Francisca, Thalita</i>) e teste o áudio.",
            "<b>4. Modo Ouvir Sempre:</b> Ative a chave no topo da tela para manter o microfone em prontidão silenciosa com a palavra-chave <i>'Sexta-Feira'</i>."
        ],
        exemplos_comandos: [
            "Sexta-Feira, que horas são?",
            "Sexta-Feira, me conte uma curiosidade sobre astronomia",
            "Sexta-Feira, qual é a previsão do tempo para o fim de semana?"
        ],
        dicas: "As preferências de IA e voz ficam salvas no seu perfil do banco de dados SQLite e persistem em qualquer dispositivo."
    },

    perfil: {
        icone: "👤",
        titulo: "Perfil do Morador & Memória Pessoal",
        categoria: "Personalização",
        resumo: "Cadastro de informações biográficas, preferências, rotinas e biometria fotográfica para reconhecimento facial.",
        passo_a_passo: [
            "Acesse a página <b>Meu Perfil</b> (/profile.html).",
            "Envie uma foto de perfil nítida para ser reconhecido nas câmeras da casa.",
            "Preencha seus dados pessoais: tipo sanguíneo, alergias, pratos favoritos, músicas, hobbies e rotinas.",
            "O agente consulta essas informações para personalizar conselhos, lembretes e respostas familiares."
        ],
        exemplos_comandos: [
            "Sexta-Feira, consulte o meu perfil e me diga quais são minhas comidas favoritas",
            "Qual é o meu tipo sanguíneo cadastrado?",
            "O que você sabe sobre mim no meu perfil?"
        ],
        dicas: "Você pode atualizar seus dados ou foto de perfil a qualquer momento sem reiniciar o servidor."
    },

    memoria_longo_prazo: {
        icone: "🧠",
        titulo: "Memória de Longo Prazo & Aprendizado Autônomo",
        categoria: "Inteligência Artificial & Memória",
        resumo: "O assistente aprende e memoriza automaticamente fatos sobre sua rotina, preferências, gostos pessoais e instruções durante as conversas diárias.",
        passo_a_passo: [
            "<b>1. Aprendizado Automático:</b> Converse normalmente com o assistente. Sempre que você mencionar gostos, regras, familiares ou preferências, a IA grava o fato no banco de dados com categoria e nível de importância.",
            "<b>2. Resgate de Memórias:</b> Quando você fizer perguntas sobre o que ele sabe sobre você ou pedir recomendações, ele consulta a base de memórias de longo prazo.",
            "<b>3. Gerenciamento Completo:</b> Você pode pedir para listar tudo o que ele lembra (<i>'O que você lembra sobre mim?'</i>) ou pedir para esquecer algo (<i>'Esqueça que meu time é o Flamengo'</i>).",
            "<b>4. Persistência Isolada:</b> Cada morador/usuário possui sua própria base de memórias protegida e isolada no SQLite."
        ],
        exemplos_comandos: [
            "Sexta-Feira, lembre-se de que meu time de coração é o Flamengo",
            "Sempre que eu pedir pizza, lembre-se que prefiro quatro queijos",
            "O que você lembra e sabe sobre mim até agora?",
            "Qual é o meu time de futebol favorito?",
            "Esqueça que eu gosto de samba"
        ],
        dicas: "As memórias mais recentes e importantes são injetadas no contexto inicial de cada diálogo, tornando as interações cada vez mais personalizadas."
    },

    musica: {
        icone: "🎵",
        titulo: "Música, Podcasts & Alto-Falante",
        categoria: "Entretenimento & Áudio",
        resumo: "Busca e reprodução contínua de músicas, bandas, gêneros musicais (samba, pagode, rock, etc.) e podcasts nos alto-falantes.",
        passo_a_passo: [
            "Peça ao assistente para tocar qualquer artista, música, gênero ou podcast por voz ou texto.",
            "O sistema busca automaticamente o fluxo de áudio no YouTube e inicia a reprodução em segundo plano com ffplay.",
            "Para parar ou pausar a qualquer momento, basta dizer <i>'Para a música'</i> ou <i>'Silêncio'</i>.",
            "Você pode perguntar <i>'Qual música está tocando?'</i> para saber a faixa atual e o tempo decorrido."
        ],
        exemplos_comandos: [
            "Sexta-Feira, toca um pagode para animar a casa",
            "Coloque um samba raiz para tocar",
            "Toca o podcast do Flow no alto-falante",
            "Para a música por favor",
            "Qual música está tocando agora?"
        ],
        dicas: "O player roda de forma assíncrona e não bloqueia a conversa ou as outras funções do assistente."
    },

    comandos_sistema: {
        icone: "💻",
        titulo: "Controle da Máquina Física (Volume, Brilho & Navegador)",
        categoria: "Hardware & Sistema Operacional",
        resumo: "Ajuste do volume físico do computador, brilho de tela/monitores e controle seguro de abas do navegador.",
        passo_a_passo: [
            "<b>1. Ative a Permissão:</b> No modal de Configurações, marque a opção <i>'Controle da Máquina Física'</i> para autorizar comandos de sistema.",
            "<b>2. Controle de Volume:</b> Peça para aumentar, diminuir, definir porcentagem (ex: <i>'Volume em 80%'</i>) ou mutar o som.",
            "<b>3. Controle de Brilho:</b> Ajuste o brilho dos monitores diretamente (ex: <i>'Aumenta o brilho da tela'</i> ou <i>'Brilho em 50%'</i>).",
            "<b>4. Navegador de Internet:</b> Abra sites ou buscas no navegador (ex: <i>'Abre o YouTube no navegador'</i>) e feche quando terminar (ex: <i>'Fecha a página'</i>).",
            "<b>5. Proteção da Casa:</b> Por segurança, o assistente nunca fecha a tela do próprio painel inteligente."
        ],
        exemplos_comandos: [
            "Aumenta o volume do computador em 20%",
            "Coloca o som no mudo",
            "Abaixa o brilho da tela",
            "Abre o YouTube no navegador",
            "Fecha a página do YouTube"
        ],
        dicas: "Os comandos funcionam tanto em ambientes GNOME/Wayland quanto X11 de forma nativa."
    },

    youtube_tutoriais: {
        icone: "📺",
        titulo: "YouTube & Transcrições de Vídeos",
        categoria: "Tutoriais & Aprendizado",
        resumo: "Busca de tutoriais do YouTube com transcrição em texto das falas para ensinar receitas, consertos e guias passo a passo.",
        passo_a_passo: [
            "Peça um tutorial prático de culinária, conserto doméstico ou aprendizado (ex: <i>'Como consertar chuveiro que não esquenta'</i>).",
            "A IA busca os melhores vídeos instrutivos no YouTube e baixa a transcrição real das falas em português.",
            "O assistente lê e sintetiza as explicações em tópicos claros e objetivos para você seguir o passo a passo."
        ],
        exemplos_comandos: [
            "Sexta-Feira, pesquise um tutorial no YouTube de como consertar torneira pingando",
            "Como fazer pudim de leite condensado passo a passo?",
            "Tutorial de como regular as marchas da bicicleta"
        ],
        dicas: "Você pode pedir para a IA resumir apenas os pontos principais ou detalhar cada ferramenta necessária."
    }
};

/**
 * Abre o modal de guia detalhado para a funcionalidade escolhida.
 * @param {string} featureKey - Chave da funcionalidade em SYSTEM_GUIDES
 */
function openFeatureGuide(featureKey = "visao_geral") {
    const guide = SYSTEM_GUIDES[featureKey] || SYSTEM_GUIDES.visao_geral;

    let modal = document.getElementById("systemFeatureGuideModal");
    if (!modal) {
        modal = document.createElement("div");
        modal.id = "systemFeatureGuideModal";
        modal.className = "fixed inset-0 z-50 bg-black/80 backdrop-blur-md hidden flex items-center justify-center p-4 transition-all duration-300";
        document.body.appendChild(modal);
    }

    // Gera lista de atalhos de outras ferramentas no topo do modal
    const navButtons = Object.keys(SYSTEM_GUIDES).map(key => {
        const item = SYSTEM_GUIDES[key];
        const isActive = key === featureKey;
        const activeClass = isActive 
            ? "bg-indigo-600 text-white font-bold shadow-md shadow-indigo-600/30" 
            : "bg-zinc-800/80 hover:bg-zinc-700 text-zinc-300";
        return `
            <button onclick="openFeatureGuide('${key}')" class="px-3 py-1.5 rounded-xl text-xs whitespace-nowrap transition flex items-center gap-1.5 ${activeClass}">
                <span>${item.icone}</span>
                <span>${item.titulo.split("&")[0].split("(")[0].trim()}</span>
            </button>
        `;
    }).join("");

    // Gera os passos de configuração
    const passosHtml = guide.passo_a_passo.map((p, idx) => `
        <li class="flex items-start gap-3 text-xs sm:text-sm text-zinc-200 leading-relaxed bg-zinc-900/60 p-3 rounded-2xl border border-zinc-800">
            <span class="w-6 h-6 rounded-full bg-indigo-600/30 text-indigo-300 border border-indigo-500/40 flex items-center justify-center text-xs font-bold shrink-0 mt-0.5">${idx + 1}</span>
            <div class="flex-1">${p}</div>
        </li>
    `).join("");

    // Gera exemplos de comandos
    const comandosHtml = guide.exemplos_comandos.map(cmd => `
        <div class="flex items-center justify-between gap-2 p-2.5 rounded-xl bg-zinc-900/80 border border-zinc-800 text-xs text-indigo-200">
            <span class="truncate font-mono">🗣️ "${cmd}"</span>
            <button onclick="copyGuideCommand('${cmd.replace(/'/g, "\\'")}')" title="Copiar comando"
                class="bg-indigo-600/30 hover:bg-indigo-600 text-indigo-300 hover:text-white px-2.5 py-1 rounded-lg text-[11px] font-bold transition shrink-0">
                Copiar
            </button>
        </div>
    `).join("");

    modal.innerHTML = `
        <div class="bg-gradient-to-b from-zinc-900 via-zinc-900 to-zinc-950 border border-zinc-700/80 rounded-3xl p-5 sm:p-7 max-w-2xl w-full shadow-2xl max-h-[90vh] flex flex-col relative overflow-hidden">
            
            <!-- Glow Decorativo -->
            <div class="absolute -top-24 -right-24 w-48 h-48 bg-indigo-500/10 rounded-full blur-3xl pointer-events-none"></div>

            <!-- HEADER DO MODAL -->
            <div class="flex items-center justify-between pb-4 border-b border-zinc-800 mb-4 shrink-0">
                <div class="flex items-center gap-3">
                    <div class="w-12 h-12 rounded-2xl bg-indigo-600/20 border border-indigo-500/40 flex items-center justify-center text-2xl shadow-lg shadow-indigo-950">
                        ${guide.icone}
                    </div>
                    <div>
                        <div class="flex items-center gap-2">
                            <span class="text-[10px] font-mono uppercase tracking-wider text-indigo-400 bg-indigo-950/60 px-2 py-0.5 rounded-md border border-indigo-800/50">${guide.categoria}</span>
                        </div>
                        <h2 class="text-lg sm:text-xl font-black text-white mt-0.5">${guide.titulo}</h2>
                    </div>
                </div>
                <button onclick="closeFeatureGuide()" class="text-zinc-400 hover:text-white bg-zinc-800 hover:bg-zinc-700 w-9 h-9 rounded-xl flex items-center justify-center text-base transition">
                    ✕
                </button>
            </div>

            <!-- CARROSSEL / SELETOR DE OUTRAS TELAS -->
            <div class="flex items-center gap-2 overflow-x-auto pb-3 mb-4 shrink-0 border-b border-zinc-800/60 scrollbar-thin">
                ${navButtons}
            </div>

            <!-- CORPO DO GUIA COM SCROLL -->
            <div class="flex-1 overflow-y-auto pr-1 space-y-5">
                
                <!-- Resumo -->
                <div class="p-4 rounded-2xl bg-indigo-950/30 border border-indigo-500/30 text-xs sm:text-sm text-indigo-100 leading-relaxed flex items-start gap-2.5">
                    <span class="text-base shrink-0">📌</span>
                    <span>${guide.resumo}</span>
                </div>

                <!-- Passo a Passo -->
                <div>
                    <h3 class="text-xs font-bold uppercase tracking-wider text-zinc-400 mb-3 flex items-center gap-1.5">
                        <span>⚙️</span> <span>Como Configurar e Usar:</span>
                    </h3>
                    <ul class="space-y-2.5">
                        ${passosHtml}
                    </ul>
                </div>

                <!-- Exemplos de Comandos -->
                <div>
                    <h3 class="text-xs font-bold uppercase tracking-wider text-zinc-400 mb-2.5 flex items-center gap-1.5">
                        <span>🗣️</span> <span>Exemplos de Comandos para Falar ou Digitar:</span>
                    </h3>
                    <div class="space-y-2">
                        ${comandosHtml}
                    </div>
                </div>

                <!-- Dica / Pro-Tip -->
                ${guide.dicas ? `
                    <div class="p-3.5 rounded-2xl bg-amber-950/20 border border-amber-500/30 text-xs text-amber-200/90 leading-relaxed flex items-start gap-2">
                        <span class="text-base shrink-0">💡</span>
                        <div><b>Dica Pro:</b> ${guide.dicas}</div>
                    </div>
                ` : ""}

            </div>

            <!-- FOOTER -->
            <div class="pt-4 mt-4 border-t border-zinc-800 flex justify-between items-center shrink-0">
                <span class="text-[11px] text-zinc-500 font-mono">Dúvidas? Pergunte à Sexta-Feira no chat</span>
                <button onclick="closeFeatureGuide()" class="bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-bold px-5 py-2.5 rounded-xl shadow-lg shadow-indigo-600/30 transition">
                    Entendi, Fechar
                </button>
            </div>

        </div>
    `;

    modal.classList.remove("hidden");
}

/**
 * Fecha o modal de guia
 */
function closeFeatureGuide() {
    const modal = document.getElementById("systemFeatureGuideModal");
    if (modal) {
        modal.classList.add("hidden");
    }
}

/**
 * Copia o comando de exemplo para a área de transferência e preenche o terminal se disponível
 */
function copyGuideCommand(cmd) {
    if (navigator.clipboard) {
        navigator.clipboard.writeText(cmd).then(() => {
            const terminalInput = document.getElementById("terminalInput");
            if (terminalInput) {
                terminalInput.value = cmd;
                terminalInput.focus();
            }
            alert(`Comando copiado:\n"${cmd}"`);
        }).catch(() => {
            prompt("Copie o comando:", cmd);
        });
    } else {
        prompt("Copie o comando:", cmd);
    }
}

// Fechar com tecla ESC
document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
        closeFeatureGuide();
    }
});

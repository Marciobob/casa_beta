/**
 * voice_agent.js - Motor Universal de Escuta de Voz & Controle Autônomo do Agente
 * Fornece o sistema completo de microfone flutuante, HUD em tempo real, escuta contínua (Wake Word),
 * síntese de voz (TTS Neural) e navegação autônoma em TODAS as telas do sistema.
 */

(function () {
    // Evita inicialização dupla
    if (window.__VOICE_AGENT_INITIALIZED__) return;

    const currentPath = window.location.pathname;
    const isDedicatedDashboard = currentPath === "/" || currentPath === "/index.html" || currentPath === "/casa.html" || currentPath === "/casa" || currentPath === "/agent";

    // Se já for dashboard dedicado com interface própria, garante compatibilidade e sai
    if (isDedicatedDashboard) {
        return;
    }

    window.__VOICE_AGENT_INITIALIZED__ = true;

    // Estado Global
    let alwaysListen = localStorage.getItem("alwaysListenSmartHome") !== "false";
    let isListening = false;
    let isSpeakingTTS = false;
    let isProcessingCommand = false;
    let isAudioPlayingActive = false;
    let isManualMicTriggered = false;
    let isWaitingCommandAfterWakeWord = false;
    let wakeWordTimer = null;
    let voiceRestartTimeout = null;
    let watchdogInterval = null;
    let ttsSafetyTimeout = null;
    let recognitionInstance = null;
    let sharedAudioContext = null;
    let silentGainNode = null;
    let silentOscillator = null;
    let speechSessionId = 0;
    let speechQueue = [];
    let isProcessingQueue = false;
    let currentPlayingAudio = null;
    let currentAudioSourceNode = null;
    let cachedHouseConfig = { broker: "test.mosquitto.org", port: 8081, rooms: [] };
    let roomStates = {};
    let mqttClient = null;

    function getAuthToken() {
        return localStorage.getItem("smartHomeToken") || "";
    }

    function getAgentName() {
        return localStorage.getItem("smartHomeAgentName") || "Sexta-Feira";
    }

    function getAiModel() {
        return localStorage.getItem("smartHomeAiModel") || "gemini-2.5-flash-lite";
    }

    function getApiKey() {
        return localStorage.getItem("geminiApiKey") || "";
    }

    function getSelectedVoice() {
        return localStorage.getItem("smartHomeVoice") || "pt-BR-FranciscaNeural";
    }

    function cleanTextForSpeech(text) {
        if (!text) return "";
        let t = text.replace(/```[\s\S]*?```/g, "");
        t = t.replace(/\[([^\]]+)\]\([^)]+\)/g, "$1");
        t = t.replace(/^#{1,6}\s+/gm, "");
        t = t.replace(/\*\*([^*]+)\*\*/g, "$1");
        t = t.replace(/\*([^*]+)\*/g, "$1");
        t = t.replace(/__([^_]+)__/g, "$1");
        t = t.replace(/_([^_]+)_/g, "$1");
        t = t.replace(/`([^`]+)`/g, "$1");
        t = t.replace(/^\s*[-*+•]\s+/gm, "");
        t = t.replace(/^\s*\d+\.\s+/gm, "");
        t = t.replace(/https?:\/\/\S+/g, "");
        t = t.replace(/www\.\S+/g, "");
        t = t.replace(/[\u{1F300}-\u{1F9FF}\u{2600}-\u{26FF}\u{2700}-\u{27BF}]/gu, "");
        return t.replace(/\s+/g, " ").trim();
    }

    // =========================================================================
    // INJEÇÃO DOS ESTILOS E COMPONENTES VISUAIS (BOTÃO + HUD + TOAST)
    // =========================================================================
    function injectStylesAndUI() {
        if (!document.getElementById("voiceAgentStyles")) {
            const style = document.createElement("style");
            style.id = "voiceAgentStyles";
            style.textContent = `
                @keyframes pulseRing {
                    0% { transform: scale(0.95); opacity: 0.8; }
                    50% { transform: scale(1.2); opacity: 0.35; }
                    100% { transform: scale(0.95); opacity: 0.8; }
                }
                @keyframes waveAnimation {
                    0%, 100% { height: 6px; }
                    50% { height: 26px; }
                }
                .animate-pulse-ring {
                    animation: pulseRing 1.8s cubic-bezier(0.4, 0, 0.6, 1) infinite;
                }
                .wave-bar {
                    animation: waveAnimation 1.2s ease-in-out infinite;
                }
                .wave-bar:nth-child(2) { animation-delay: 0.15s; }
                .wave-bar:nth-child(3) { animation-delay: 0.3s; }
                .wave-bar:nth-child(4) { animation-delay: 0.45s; }
                .wave-bar:nth-child(5) { animation-delay: 0.6s; }
                .glass-hud {
                    background: rgba(18, 18, 22, 0.94);
                    backdrop-filter: blur(20px);
                    -webkit-backdrop-filter: blur(20px);
                }
            `;
            document.head.appendChild(style);
        }

        // 1. Botão Flutuante de Voz (Microfone)
        if (!document.getElementById("floatingVoiceBtn")) {
            const micContainer = document.createElement("div");
            micContainer.id = "globalFloatingMicContainer";
            micContainer.className = "fixed bottom-6 right-6 z-50 flex items-center gap-3";
            micContainer.innerHTML = `
                <div id="micPulseEffect"
                    class="hidden absolute -inset-3 bg-indigo-500 rounded-full animate-pulse-ring opacity-75 pointer-events-none"></div>
                <button id="floatingVoiceBtn" onclick="toggleVoiceAssistant()" title="Ativar Microfone / Falar com o Agente"
                    class="relative w-16 h-16 rounded-full bg-gradient-to-tr from-indigo-600 via-indigo-500 to-purple-500 text-white flex items-center justify-center shadow-2xl hover:scale-105 active:scale-95 transition-all duration-300 border-2 border-indigo-300/40 cursor-pointer">
                    <svg id="micIcon" class="w-8 h-8 transition-transform duration-300" fill="none" stroke="currentColor"
                        viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2"
                            d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z">
                        </path>
                    </svg>
                    <svg id="stopIcon" class="w-7 h-7 hidden text-red-200" fill="currentColor" viewBox="0 0 20 20">
                        <rect x="5" y="5" width="10" height="10" rx="2" />
                    </svg>
                </button>
            `;
            document.body.appendChild(micContainer);
        }

        // 2. HUD / Painel Informativo do Agente
        if (!document.getElementById("voiceHud")) {
            const hud = document.createElement("div");
            hud.id = "voiceHud";
            hud.className = "fixed bottom-24 right-6 left-6 md:left-auto md:w-96 max-h-[82vh] flex flex-col glass-hud rounded-3xl border border-indigo-500/30 p-5 shadow-2xl transition-all duration-300 z-40 hidden";
            hud.innerHTML = `
                <div class="flex items-center justify-between pb-3 border-b border-zinc-800 shrink-0">
                    <div class="flex items-center gap-2">
                        <div class="w-2.5 h-2.5 rounded-full bg-indigo-400 animate-ping"></div>
                        <span id="hudAgentTitle" class="font-bold text-sm text-indigo-300">Assistente ${getAgentName()}</span>
                    </div>
                    <button onclick="closeVoiceHud()"
                        class="text-zinc-400 hover:text-white text-xs px-2 py-1 bg-zinc-800/80 rounded-lg cursor-pointer">✕</button>
                </div>

                <div class="my-4 flex items-center gap-3 shrink-0">
                    <div id="voiceWaveAnimation" class="flex items-end gap-1 h-7">
                        <div class="w-1.5 bg-indigo-500 rounded-full wave-bar"></div>
                        <div class="w-1.5 bg-indigo-400 rounded-full wave-bar"></div>
                        <div class="w-1.5 bg-purple-500 rounded-full wave-bar"></div>
                        <div class="w-1.5 bg-indigo-400 rounded-full wave-bar"></div>
                        <div class="w-1.5 bg-indigo-500 rounded-full wave-bar"></div>
                    </div>
                    <div class="flex-1 min-w-0">
                        <p id="voiceStatusText" class="text-xs text-zinc-400 font-medium">Ouvindo...</p>
                        <p id="voiceTranscriptText" class="text-sm font-semibold text-zinc-100 italic truncate mt-0.5">"..."</p>
                    </div>
                </div>

                <div id="geminiResponseBox"
                    class="hidden my-2 p-3 bg-zinc-900/90 rounded-2xl border border-indigo-500/20 text-xs text-zinc-200 flex-1 overflow-hidden flex flex-col">
                    <div class="flex items-center justify-between font-bold text-indigo-400 mb-1.5 shrink-0">
                        <span>🤖 Resposta do Agente:</span>
                    </div>
                    <div id="geminiResponseText" class="overflow-y-auto max-h-48 leading-relaxed space-y-2 pr-1"></div>
                </div>

                <form id="voiceManualForm" onsubmit="handleManualVoiceCommand(event)" class="flex items-center gap-2 mt-2 shrink-0">
                    <input id="voiceTextInput" type="text" placeholder="Falar ou digitar comando..."
                        class="flex-1 bg-zinc-800/90 border border-zinc-700/80 rounded-xl px-3.5 py-2 text-xs text-white placeholder-zinc-500 focus:outline-none focus:border-indigo-500">
                    <button type="submit"
                        class="bg-indigo-600 hover:bg-indigo-500 text-white px-3 py-2 rounded-xl text-xs font-bold transition shadow-md shadow-indigo-600/30 cursor-pointer">
                        Enviar
                    </button>
                </form>
            `;
            document.body.appendChild(hud);
        }

        // 3. Container de Toast de Navegação e Notificações
        if (!document.getElementById("screenToastContainer")) {
            const toastContainer = document.createElement("div");
            toastContainer.id = "screenToastContainer";
            toastContainer.className = "fixed top-5 right-5 z-[99999] flex flex-col gap-3 max-w-sm w-full pointer-events-none transition-all";
            document.body.appendChild(toastContainer);
        }
    }

    function showVoiceHud() {
        const hud = document.getElementById("voiceHud");
        if (hud) hud.classList.remove("hidden");
    }

    function closeVoiceHud() {
        const hud = document.getElementById("voiceHud");
        if (hud) hud.classList.add("hidden");
    }

    function setVoiceStatus(icon, text, isAnimatingWave) {
        const statusEl = document.getElementById("voiceStatusText");
        const wave = document.getElementById("voiceWaveAnimation");
        if (statusEl) statusEl.innerText = `${icon} ${text}`;
        if (wave) {
            if (isAnimatingWave) wave.classList.remove("opacity-20");
            else wave.classList.add("opacity-20");
        }
    }

    function setVoiceTranscript(text, isItalic) {
        const el = document.getElementById("voiceTranscriptText");
        if (el) {
            el.innerText = text;
            if (isItalic) el.classList.add("italic");
            else el.classList.remove("italic");
        }
    }

    function showResponse(text) {
        const box = document.getElementById("geminiResponseBox");
        const textEl = document.getElementById("geminiResponseText");
        if (textEl) {
            textEl.innerHTML = renderFormattedChatHtml(text);
        }
        if (box) box.classList.remove("hidden");
    }

    function renderScreenToastNotification(notif) {
        const container = document.getElementById("screenToastContainer");
        if (!container) return;

        const toast = document.createElement("div");
        toast.className = "pointer-events-auto bg-zinc-900/95 border border-indigo-500/50 rounded-2xl p-4 shadow-2xl flex items-start gap-3 transform transition-all duration-300 text-white";
        toast.innerHTML = `
            <div class="w-8 h-8 rounded-xl bg-indigo-600 flex items-center justify-center shrink-0 text-sm shadow-md">🤖</div>
            <div class="flex-1 min-w-0">
                <h4 class="text-xs font-bold text-indigo-300">${notif.title || "Agente Inteligente"}</h4>
                <p class="text-xs text-zinc-200 mt-0.5 leading-relaxed">${notif.message}</p>
            </div>
            <button onclick="this.parentElement.remove()" class="text-zinc-400 hover:text-white text-xs p-1">✕</button>
        `;
        container.appendChild(toast);
        setTimeout(() => {
            if (toast.parentElement) toast.remove();
        }, 6000);
    }

    // =========================================================================
    // MOTOR DE ÁUDIO & DESBLOQUEIO DE AUTOPLAY (WEB AUDIO API + HTML5 AUDIO)
    // =========================================================================
    function getSharedAudioContext() {
        if (!sharedAudioContext) {
            const AudioCtx = window.AudioContext || window.webkitAudioContext;
            if (AudioCtx) sharedAudioContext = new AudioCtx();
        }
        return sharedAudioContext;
    }

    function primeKeepAliveNode(ctx) {
        if (!ctx) return;
        try {
            if (!silentGainNode) {
                silentGainNode = ctx.createGain();
                silentGainNode.gain.value = 0.00001;
                silentGainNode.connect(ctx.destination);

                silentOscillator = ctx.createOscillator();
                silentOscillator.frequency.value = 440;
                silentOscillator.connect(silentGainNode);
                try { silentOscillator.start(0); } catch (e) { }
            }
        } catch (e) { }
    }

    function unlockAudioContext() {
        try {
            const ctx = getSharedAudioContext();
            if (ctx && ctx.state === "suspended") ctx.resume().catch(() => { });
            if ("speechSynthesis" in window && window.speechSynthesis.paused) {
                window.speechSynthesis.resume();
            }
        } catch (e) { }
    }

    function primeAudioEngine() {
        unlockAudioContext();
        try {
            const ctx = getSharedAudioContext();
            if (ctx && ctx.state === "running") {
                primeKeepAliveNode(ctx);
            }
        } catch (e) { }
    }

    function playAudioBlob(blob) {
        return new Promise((resolve) => {
            if (!blob) { resolve(false); return; }
            try {
                isAudioPlayingActive = true;
                stopVoiceRecognition();

                if (currentPlayingAudio) {
                    try {
                        currentPlayingAudio.pause();
                        currentPlayingAudio.src = "";
                    } catch (e) { }
                    currentPlayingAudio = null;
                }

                const audioUrl = URL.createObjectURL(blob);
                const audio = new Audio(audioUrl);
                currentPlayingAudio = audio;
                audio.preload = "auto";

                let isDone = false;
                let safetyWatchdog = null;

                const cleanup = (success) => {
                    if (!isDone) {
                        isDone = true;
                        if (safetyWatchdog) clearTimeout(safetyWatchdog);
                        audio.onended = null;
                        audio.onerror = null;
                        if (currentPlayingAudio === audio) currentPlayingAudio = null;
                        try { URL.revokeObjectURL(audioUrl); } catch (e) { }
                        resolve(success);
                    }
                };

                audio.onended = () => cleanup(true);
                audio.onerror = () => cleanup(false);
                safetyWatchdog = setTimeout(() => cleanup(true), 40000);

                const playPromise = audio.play();
                if (playPromise !== undefined) {
                    playPromise.catch(() => cleanup(false));
                }
            } catch (e) {
                isAudioPlayingActive = false;
                resolve(false);
            }
        });
    }

    async function fetchAudioItem(text, voice) {
        unlockAudioContext();
        const token = getAuthToken();
        const res = await fetch("/api/tts", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Authorization": token ? `Bearer ${token}` : ""
            },
            body: JSON.stringify({
                text: text,
                voice: voice,
                rate: "+12%"
            })
        });

        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const blob = await res.blob();
        return { blob };
    }

    function enqueueSpeech(text, isFinal = false) {
        const cleanText = cleanTextForSpeech(text);
        if (!cleanText) return;

        const selectedVoice = getSelectedVoice();
        const itemPromise = (selectedVoice !== "browser-native")
            ? fetchAudioItem(cleanText, selectedVoice).catch(() => null)
            : Promise.resolve(null);

        speechQueue.push({
            text: cleanText,
            isFinal: isFinal,
            voice: selectedVoice,
            itemPromise: itemPromise
        });

        if (!isProcessingQueue) {
            processSpeechQueue();
        }
    }

    async function processSpeechQueue() {
        if (speechQueue.length === 0) {
            isProcessingQueue = false;
            isSpeakingTTS = false;
            isAudioPlayingActive = false;
            if (ttsSafetyTimeout) clearTimeout(ttsSafetyTimeout);
            clearTimeout(voiceRestartTimeout);

            if (alwaysListen && !isProcessingCommand) {
                voiceRestartTimeout = setTimeout(() => {
                    if (alwaysListen && !isListening && !isSpeakingTTS && !isProcessingCommand && !isAudioPlayingActive && speechQueue.length === 0) {
                        startVoiceRecognition();
                    }
                }, 120);
            }
            return;
        }

        const thisSession = speechSessionId;
        isProcessingQueue = true;
        isSpeakingTTS = true;
        isAudioPlayingActive = true;
        stopVoiceRecognition();

        const item = speechQueue.shift();

        if (ttsSafetyTimeout) clearTimeout(ttsSafetyTimeout);
        ttsSafetyTimeout = setTimeout(() => {
            clearSpeechQueue();
            if (alwaysListen && !isProcessingCommand) startVoiceRecognition();
        }, 35000);

        try {
            if (item.voice === "browser-native" || !navigator.onLine) {
                await speakWithBrowserNativeAsync(item.text);
            } else {
                const audioData = await item.itemPromise;
                if (thisSession !== speechSessionId || !isSpeakingTTS || !isProcessingQueue) return;

                let played = false;
                if (audioData && audioData.blob) {
                    played = await playAudioBlob(audioData.blob);
                }
                if (thisSession !== speechSessionId || !isSpeakingTTS || !isProcessingQueue) return;

                if (!played) {
                    await speakWithBrowserNativeAsync(item.text);
                }
            }
        } catch (err) {
            if (thisSession === speechSessionId && isSpeakingTTS && isProcessingQueue) {
                try { await speakWithBrowserNativeAsync(item.text); } catch (e) { }
            }
        }

        if (thisSession !== speechSessionId || !isSpeakingTTS || !isProcessingQueue) return;
        processSpeechQueue();
    }

    function speakWithBrowserNativeAsync(text) {
        return new Promise((resolve) => {
            if (!("speechSynthesis" in window)) { resolve(); return; }
            try {
                isAudioPlayingActive = true;
                stopVoiceRecognition();
                window.speechSynthesis.cancel();
                window.speechSynthesis.resume();

                const utterance = new SpeechSynthesisUtterance(text);
                utterance.lang = "pt-BR";
                utterance.rate = 1.15;
                const voices = window.speechSynthesis.getVoices();
                const ptVoice = voices.find(v => v.lang.includes("pt-BR") || v.lang.includes("pt"));
                if (ptVoice) utterance.voice = ptVoice;

                let isDone = false;
                const finish = () => {
                    if (!isDone) {
                        isDone = true;
                        utterance.onend = null;
                        utterance.onerror = null;
                        resolve();
                    }
                };
                utterance.onend = finish;
                utterance.onerror = finish;
                setTimeout(finish, Math.max(3000, Math.min(text.length * 100, 20000)));

                window.speechSynthesis.speak(utterance);
            } catch (e) {
                resolve();
            }
        });
    }

    function silenciarAudio(notify = true) {
        speechSessionId++;
        clearSpeechQueue();
        if (currentPlayingAudio) {
            try {
                currentPlayingAudio.pause();
                currentPlayingAudio.currentTime = 0;
                currentPlayingAudio.src = "";
            } catch (e) { }
            currentPlayingAudio = null;
        }
        if ("speechSynthesis" in window) {
            try { window.speechSynthesis.cancel(); } catch (e) { }
        }
        isSpeakingTTS = false;
        isAudioPlayingActive = false;
        isProcessingQueue = false;

        if (notify) {
            setVoiceStatus("⏹️", "Áudio interrompido.", false);
        }

        if (alwaysListen && !isProcessingCommand) {
            clearTimeout(voiceRestartTimeout);
            voiceRestartTimeout = setTimeout(() => {
                if (alwaysListen && !isListening) {
                    startVoiceRecognition();
                }
            }, 50);
        }
    }

    function clearSpeechQueue() {
        speechSessionId++;
        speechQueue = [];
        isProcessingQueue = false;
        isSpeakingTTS = false;
        isAudioPlayingActive = false;
        clearTimeout(voiceRestartTimeout);
        if (ttsSafetyTimeout) clearTimeout(ttsSafetyTimeout);
        if ("speechSynthesis" in window) {
            try { window.speechSynthesis.cancel(); } catch (e) { }
        }
    }

    function speakResponse(text) {
        enqueueSpeech(text, true);
    }

    function speakIntermediateStatus(text) {
        enqueueSpeech(text, false);
    }

    // =========================================================================
    // RECONHECIMENTO DE VOZ & WAKE WORD ("SEXTA-FEIRA")
    // =========================================================================
    function normalizeText(text) {
        return text
            .toLowerCase()
            .normalize("NFD")
            .replace(/[\u0300-\u036f]/g, "")
            .trim();
    }

    function getWakeWordPatterns(agentName) {
        const raw = (agentName || "Sexta-Feira").trim();
        const normalized = normalizeText(raw);
        const patterns = new Set();

        patterns.add(normalized);
        patterns.add(normalized.replace(/[-\s_]+/g, " "));
        patterns.add(normalized.replace(/[-\s_]+/g, "-"));
        patterns.add(normalized.replace(/[-\s_]+/g, ""));

        if (normalized.includes("sexta") || normalized.includes("cesta") || normalized.includes("sesta")) {
            patterns.add("sexta-feira");
            patterns.add("sexta feira");
            patterns.add("sextafeira");
            patterns.add("sexta");
            patterns.add("cesta-feira");
            patterns.add("cesta feira");
            patterns.add("cesta");
            patterns.add("sesta feira");
            patterns.add("sesta");
            patterns.add("6a feira");
            patterns.add("6 feira");
            patterns.add("sexta f");
            patterns.add("seta feira");
        } else if (normalized === "atena" || normalized === "athena" || normalized === "antena") {
            patterns.add("atena");
            patterns.add("athena");
            patterns.add("antena");
            patterns.add("atenas");
            patterns.add("athenas");
        } else if (normalized === "jarvis") {
            patterns.add("jarvis");
            patterns.add("jarves");
            patterns.add("jarviz");
            patterns.add("iárvis");
        } else if (normalized === "computador") {
            patterns.add("computador");
            patterns.add("computadora");
        }

        const baseList = Array.from(patterns);
        const prefixes = ["ei ", "hey ", "ok ", "ola ", "olá ", "oi ", "e ai ", "e aí ", "ou ", "o ", "ô ", "a ", "fala ", "fala aí ", "por favor "];
        baseList.forEach(nameVariant => {
            prefixes.forEach(p => {
                patterns.add(p + nameVariant);
            });
        });

        return Array.from(patterns).filter(Boolean);
    }

    function extractWakeWordAndCommand(text, agentName) {
        if (!text || !text.trim()) return { isWake: false, command: "" };
        const norm = normalizeText(text);
        const patterns = getWakeWordPatterns(agentName);
        patterns.sort((a, b) => b.length - a.length);

        const escapedNames = patterns.map(n => normalizeText(n).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join("|");
        const wakeRegex = new RegExp(`(?:^|\\b)(?:${escapedNames})[\\s,:\\.-]*(.*)`, "i");
        const match = norm.match(wakeRegex);

        if (!match) {
            return { isWake: false, command: "" };
        }

        const cmdNorm = match[1].trim();
        if (!cmdNorm) {
            return { isWake: true, command: "" };
        }

        const wakePartLength = text.length - match[1].length;
        let originalCmd = text.substring(wakePartLength).replace(/^[\s,.:;!?-]+/, "").trim();
        originalCmd = originalCmd.replace(/^(?:por favor|por gentileza|faz favor)[,\s]*/i, "").trim();
        originalCmd = originalCmd.replace(/^[\s,.:;!?-]+/, "").trim();

        return { isWake: true, command: originalCmd || cmdNorm };
    }

    function isStopTalkingCommand(rawText) {
        if (!rawText) return false;
        const norm = normalizeText(rawText).trim();
        if (!norm) return false;

        const isActionOrContent = /\b(musica|som|cancao|faixa|playlist|tocar|luz|lampada|ventilador|quarto|sala|cozinha|escritorio|garagem|alarme|timer|tarefa|nota|agenda|email|contato|camera|video|youtube|pesquisa)\b/i.test(norm);
        if (isActionOrContent) return false;

        const stopKeywords = [
            "para", "pare", "parar", "parou", "pare por favor", "para por favor",
            "silencio", "silenciar", "silencie", "silencia",
            "cala a boca", "calada", "calado", "fica quieta", "fica quieto", "quieta", "quieto",
            "chega", "basta", "ja deu", "para de falar", "parar de falar",
            "cancela", "cancelar", "stop", "shh", "mudo", "mutar"
        ];
        return stopKeywords.some(sw => norm === sw || norm.startsWith(sw + " ") || norm.endsWith(" " + sw));
    }

    function createFreshRecognition() {
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        if (!SpeechRecognition) return null;

        if (recognitionInstance) {
            try {
                recognitionInstance.onstart = null;
                recognitionInstance.onresult = null;
                recognitionInstance.onerror = null;
                recognitionInstance.onend = null;
                recognitionInstance.abort();
            } catch (e) { }
            recognitionInstance = null;
        }

        const rec = new SpeechRecognition();
        rec.lang = "pt-BR";
        rec.continuous = false;
        rec.interimResults = true;
        rec.maxAlternatives = 1;

        let latestHeardText = "";

        rec.onstart = () => {
            isListening = true;
            latestHeardText = "";
            const pulse = document.getElementById("micPulseEffect");
            if (pulse) pulse.classList.remove("hidden");
            const mic = document.getElementById("micIcon");
            if (mic) mic.classList.add("hidden");
            const stop = document.getElementById("stopIcon");
            if (stop) stop.classList.remove("hidden");

            if (alwaysListen) {
                const agentName = getAgentName();
                if (!isWaitingCommandAfterWakeWord) {
                    setVoiceStatus("👂", `Ouvindo... Diga "${agentName}"`, true);
                }
            } else {
                setVoiceStatus("🎙️", "Ouvindo... Fale agora", true);
            }
        };

        rec.onresult = (event) => {
            if (isSpeakingTTS || isProcessingCommand || isAudioPlayingActive) {
                latestHeardText = "";
                return;
            }

            let fullTranscript = "";
            for (let i = 0; i < event.results.length; ++i) {
                fullTranscript += event.results[i][0].transcript + " ";
            }

            const currentText = fullTranscript.trim();
            if (!currentText) return;

            latestHeardText = currentText;
            showVoiceHud();
            setVoiceTranscript(`"${currentText}"`, false);
        };

        rec.onerror = (event) => {
            if (event.error === "not-allowed") {
                setVoiceStatus("⚠️", "Permissão de microfone negada", false);
                alwaysListen = false;
            }
        };

        rec.onend = () => {
            isListening = false;
            const pulse = document.getElementById("micPulseEffect");
            if (pulse) pulse.classList.add("hidden");
            const mic = document.getElementById("micIcon");
            if (mic) mic.classList.remove("hidden");
            const stop = document.getElementById("stopIcon");
            if (stop) stop.classList.add("hidden");

            const wasManual = isManualMicTriggered;
            isManualMicTriggered = false;

            if (latestHeardText && !isSpeakingTTS && !isProcessingCommand && !isAudioPlayingActive) {
                const textToProcess = latestHeardText;
                latestHeardText = "";
                if (wasManual) {
                    showVoiceHud();
                    setVoiceStatus("✨", "Executando comando...", true);
                    processCommandWithApi(textToProcess);
                } else if (alwaysListen) {
                    handleWakeWordDetection(textToProcess);
                } else {
                    showVoiceHud();
                    setVoiceStatus("✨", "Executando comando...", true);
                    processCommandWithApi(textToProcess);
                }
            }

            if (alwaysListen && !isSpeakingTTS && !isProcessingCommand && !isAudioPlayingActive && speechQueue.length === 0) {
                clearTimeout(voiceRestartTimeout);
                voiceRestartTimeout = setTimeout(() => {
                    if (alwaysListen && !isListening && !isSpeakingTTS && !isProcessingCommand && !isAudioPlayingActive && speechQueue.length === 0) {
                        startVoiceRecognition();
                    }
                }, 80);
            }
        };

        return rec;
    }

    function handleWakeWordDetection(text) {
        if (!text || !text.trim()) return;
        if (isProcessingCommand || isSpeakingTTS || isAudioPlayingActive) return;
        const norm = normalizeText(text);
        const agentName = getAgentName();

        const { isWake, command } = extractWakeWordAndCommand(text, agentName);

        if (isWake) {
            if (isStopTalkingCommand(command) || isStopTalkingCommand(norm)) {
                silenciarAudio(true);
                return;
            }

            if (command.length > 1) {
                clearTimeout(wakeWordTimer);
                isWaitingCommandAfterWakeWord = false;
                showVoiceHud();
                setVoiceStatus("✨", "Processando comando...", true);
                setVoiceTranscript(`"${agentName}, ${command}"`, false);
                processCommandWithApi(command);
                return;
            }

            if (!isWaitingCommandAfterWakeWord) {
                isWaitingCommandAfterWakeWord = true;
                showVoiceHud();
                setVoiceStatus("⚡", `Sim! Diga o comando agora...`, true);
                setVoiceTranscript(`"${agentName}..." (Aguardando instrução...)`, false);

                speakResponse("Sim, estou ouvindo!");

                clearTimeout(wakeWordTimer);
                wakeWordTimer = setTimeout(() => {
                    isWaitingCommandAfterWakeWord = false;
                    setVoiceStatus("💤", "Aguardando ativação...", false);
                }, 8000);
            }
            return;
        }

        if (isWaitingCommandAfterWakeWord && text.trim()) {
            clearTimeout(wakeWordTimer);
            isWaitingCommandAfterWakeWord = false;
            if (isStopTalkingCommand(norm)) {
                silenciarAudio(true);
                return;
            }
            showVoiceHud();
            setVoiceStatus("✨", "Executando comando...", true);
            setVoiceTranscript(`"${text.trim()}"`, false);
            processCommandWithApi(text.trim());
        }
    }

    function updateAlwaysListenUI() {
        const dot = document.getElementById("alwaysListenDot");
        const txt = document.getElementById("alwaysListenText");
        const btn = document.getElementById("alwaysListenBtn");
        if (dot && txt) {
            if (alwaysListen) {
                dot.className = "w-2.5 h-2.5 rounded-full bg-green-500 animate-pulse";
                txt.innerText = "🎙️ Ouvir Sempre: Ativo";
                if (btn) {
                    btn.classList.add("border-green-600/50");
                }
            } else {
                dot.className = "w-2.5 h-2.5 rounded-full bg-zinc-500";
                txt.innerText = "🎙️ Ouvir Sempre: Inativo";
                if (btn) {
                    btn.classList.remove("border-green-600/50");
                }
            }
        }
    }

    window.toggleAlwaysListen = function () {
        alwaysListen = !alwaysListen;
        localStorage.setItem("alwaysListenSmartHome", alwaysListen ? "true" : "false");
        updateAlwaysListenUI();
        if (alwaysListen) {
            primeAudioEngine();
            startVoiceRecognition();
            startContinuousWatchdog();
            setVoiceStatus("🎙️", "Escuta contínua ativada", true);
            speakResponse("Escuta contínua ativada. Pode me chamar pelo nome a qualquer momento.");
        } else {
            stopVoiceRecognition();
            setVoiceStatus("⏹️", "Escuta contínua desativada", false);
            speakResponse("Escuta contínua desativada.");
        }
    };

    window.closeVoiceHud = function () {
        const hud = document.getElementById("voiceHud");
        if (hud) hud.classList.add("hidden");
    };

    window.showVoiceHud = function () {
        const hud = document.getElementById("voiceHud");
        if (hud) hud.classList.remove("hidden");
    };

    window.toggleVoiceAssistant = function () {
        unlockAudioContext();

        if (isSpeakingTTS || isAudioPlayingActive || speechQueue.length > 0) {
            silenciarAudio(true);
            return;
        }

        if (isListening) {
            isManualMicTriggered = false;
            stopVoiceRecognition();
            setVoiceStatus("⏹️", "Microfone desligado", false);
        } else {
            isManualMicTriggered = true;
            window.showVoiceHud();
            const agentName = getAgentName();
            setVoiceStatus("🎙️", "Ouvindo... Fale seu comando agora", true);
            setVoiceTranscript(`"..."`, false);
            startVoiceRecognition();
        }
    };

    function startVoiceRecognition() {
        if (isListening || isSpeakingTTS || isProcessingCommand || isAudioPlayingActive || speechQueue.length > 0) return;
        try {
            recognitionInstance = createFreshRecognition();
            if (recognitionInstance) recognitionInstance.start();
        } catch (e) {
            clearTimeout(voiceRestartTimeout);
            voiceRestartTimeout = setTimeout(() => {
                if (alwaysListen && !isListening && !isSpeakingTTS && !isProcessingCommand && !isAudioPlayingActive && speechQueue.length === 0) {
                    startVoiceRecognition();
                }
            }, 400);
        }
    }

    function stopVoiceRecognition() {
        clearTimeout(voiceRestartTimeout);
        if (recognitionInstance) {
            try {
                recognitionInstance.onstart = null;
                recognitionInstance.onresult = null;
                recognitionInstance.onerror = null;
                recognitionInstance.onend = null;
                try { recognitionInstance.stop(); } catch (e) { }
            } catch (e) { }
            recognitionInstance = null;
        }
        isListening = false;
        const pulse = document.getElementById("micPulseEffect");
        if (pulse) pulse.classList.add("hidden");
        const mic = document.getElementById("micIcon");
        if (mic) mic.classList.remove("hidden");
        const stop = document.getElementById("stopIcon");
        if (stop) stop.classList.add("hidden");
    }

    window.handleManualVoiceCommand = function (e) {
        if (e) e.preventDefault();
        const input = document.getElementById("voiceTextInput");
        if (!input) return;
        const cmd = input.value.trim();
        if (!cmd) return;

        input.value = "";
        window.showVoiceHud();
        setVoiceTranscript(`"${cmd}"`, false);
        processCommandWithApi(cmd);
    };

    window.handleManualCommand = window.handleManualVoiceCommand;

    // =========================================================================
    // FEEDBACK RÁPIDO & COMUNICAÇÃO COM O AGENTE (FASTAPI STREAMING)
    // =========================================================================
    function getAgentFeedbackPhrase(commandText) {
        const raw = normalizeText(commandText || "");
        const isMusic = /\b(tocar|toca|toque|escutar|musica|musicas|samba|rock|podcast|som|silencio)\b/.test(raw);
        const isSearch = /\b(pesquis|procur|busc|quem|onde|quando|quanto|qual|noticia|clima|tempo|previsao|cotacao|explique|o que e)\b/.test(raw);
        const isHome = /\b(luz|luzes|lampada|lampadas|ligar|ligue|desligar|desligue|apagar|apague|acender|acenda|camera|quarto|sala|cozinha|garagem|porta)\b/.test(raw);

        if (isMusic) return "Preparando a reprodução...";
        if (isSearch) return "Pesquisando para você...";
        if (isHome) return "Verificando os dispositivos...";
        return "Processando sua solicitação...";
    }

    function renderFormattedChatHtml(rawText) {
        if (!rawText) return "";
        let safe = rawText
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;");

        // Code blocks
        safe = safe.replace(/```([\s\S]*?)```/g, '<pre class="my-1 p-2 bg-zinc-950 rounded-lg text-emerald-400 font-mono text-[11px] overflow-x-auto"><code>$1</code></pre>');
        // Links
        safe = safe.replace(/\[([^\]]+)\]\((https?:\/\/[^\s\)]+)\)/g, '<a href="$2" target="_blank" class="text-indigo-400 hover:underline">$1</a>');
        // Bold
        safe = safe.replace(/\*\*([^*]+)\*\*/g, '<strong class="font-bold text-white">$1</strong>');
        // Line breaks
        safe = safe.replace(/\n/g, '<br>');
        return safe;
    }

    async function processCommandWithApi(userCommand) {
        if (!userCommand || !userCommand.trim()) return;
        const cleanCmd = userCommand.trim();

        if (isStopTalkingCommand(cleanCmd)) {
            silenciarAudio(true);
            isProcessingCommand = false;
            return;
        }

        primeAudioEngine();
        if (isProcessingCommand) return;
        isProcessingCommand = true;
        clearSpeechQueue();

        const feedbackPhrase = getAgentFeedbackPhrase(userCommand);
        setVoiceStatus("⚡", feedbackPhrase, true);
        showResponse(`⏳ ${feedbackPhrase}`);
        speakIntermediateStatus(feedbackPhrase);

        const token = getAuthToken();
        const allRooms = (cachedHouseConfig && cachedHouseConfig.rooms) || [];
        const roomsPayload = allRooms.map(r => ({ name: r.name, topic: r.topic }));

        let currentUserEmail = "";
        try {
            const userObj = JSON.parse(localStorage.getItem("smartHomeUser") || "{}");
            currentUserEmail = userObj.email || "";
        } catch (e) { }

        const payload = {
            message: userCommand,
            api_key: getApiKey(),
            model: getAiModel(),
            agent_name: getAgentName(),
            rooms: roomsPayload,
            rooms_state: roomStates,
            broker: (cachedHouseConfig && cachedHouseConfig.broker) || "test.mosquitto.org",
            port: 1883,
            user_email: currentUserEmail
        };

        try {
            const res = await fetch("/api/chat/stream", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "Authorization": token ? `Bearer ${token}` : ""
                },
                body: JSON.stringify(payload)
            });

            if (!res.ok) {
                const errData = await res.json().catch(() => ({}));
                throw new Error(errData.detail || `HTTP ${res.status}`);
            }

            let finalReply = "";
            let finalSpokenReply = "";
            let finalActions = [];

            if (res.body && res.body.getReader) {
                const reader = res.body.getReader();
                const decoder = new TextDecoder("utf-8");
                let buffer = "";

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;
                    buffer += decoder.decode(value, { stream: true });
                    const lines = buffer.split("\n\n");
                    buffer = lines.pop();

                    for (const block of lines) {
                        for (const line of block.split("\n")) {
                            if (line.startsWith("data: ")) {
                                const jsonStr = line.slice(6).trim();
                                if (!jsonStr) continue;
                                try {
                                    const ev = JSON.parse(jsonStr);
                                    if (ev.type === "status") {
                                        setVoiceStatus("🔄", ev.message, true);
                                        showResponse(`⏳ ${ev.message}`);
                                    } else if (ev.type === "final") {
                                        finalReply = ev.reply || "";
                                        finalSpokenReply = ev.spoken_reply || "";
                                        finalActions = ev.actions || [];
                                    } else if (ev.type === "error") {
                                        throw new Error(ev.message || "Erro no agente");
                                    }
                                } catch (errJson) { }
                            }
                        }
                    }
                }
            } else {
                const data = await res.json();
                finalReply = data.reply || "";
                finalSpokenReply = data.spoken_reply || "";
                finalActions = data.actions || [];
            }

            // Fala e prepara texto da resposta
            const reply = finalReply || "Comando processado com sucesso.";
            const textToSpeak = finalSpokenReply || cleanTextForSpeech(reply);

            // Executa ações retornadas (Navegação, Modais, MQTT) passando textToSpeak
            if (finalActions && Array.isArray(finalActions)) {
                for (const act of finalActions) {
                    handleUniversalUiAction(act, textToSpeak);
                }
            }

            setVoiceStatus("✅", "Concluído! 🤖", false);
            showResponse(reply);
            speakResponse(textToSpeak);

        } catch (e) {
            console.error("[VoiceAgent API Error]:", e);
            setVoiceStatus("❌", `Erro: ${e.message}`, false);
            showResponse(`Falha: ${e.message}`);
            speakResponse("Desculpe, ocorreu uma falha ao processar.");
        } finally {
            setTimeout(() => {
                isProcessingCommand = false;
            }, 800);
        }
    }

    function handleUniversalUiAction(action, textToSpeak) {
        if (!action) return false;
        const type = action.type || action.action_type;

        // 1. Navegação Autônoma de Telas
        if (type === "ui_navigate" || type === "navigate") {
            const target = action.target || action.url || "/";
            const cur = window.location.pathname;
            const isCur = (target === cur) || 
                          (target === "/" && (cur === "/index.html" || cur === "/agent")) ||
                          (target === "/casa.html" && cur === "/casa") ||
                          (target === "/config/config.html" && cur === "/config") ||
                          (target === "/profile.html" && cur === "/profile");

            if (textToSpeak) {
                try {
                    sessionStorage.setItem("smartHomePendingSpeech", textToSpeak);
                    localStorage.setItem("smartHomePendingSpeech", textToSpeak);
                } catch (e) { }
            }

            renderScreenToastNotification({
                id: "nav_" + Date.now(),
                title: "🧭 Navegação do Agente",
                message: `Redirecionando para ${action.name || target}...`
            });

            if (!isCur) {
                setTimeout(() => {
                    window.location.href = target;
                }, 1400);
            }
            return true;
        }

        // 2. Abertura e Fechamento de Modais e Ações de Tela
        if (type === "ui_modal" || type === "modal") {
            const verb = (action.action || action.action_type || "open").toLowerCase();
            const modalName = (action.modal || action.name || "").toLowerCase();

            if (verb.includes("open") || verb.includes("abrir")) {
                if (modalName.includes("guia") || modalName.includes("ajuda") || modalName.includes("manual") || modalName.includes("tutorial")) {
                    if (typeof openFeatureGuide === "function") openFeatureGuide(action.topic || "visao_geral");
                } else if (modalName.includes("chave") || modalName.includes("api") || modalName.includes("ia") || modalName.includes("voz") || modalName.includes("config") || modalName.includes("ajuste") || modalName.includes("conexao") || modalName.includes("conexão")) {
                    if (typeof openVoiceApiKeyModal === "function") openVoiceApiKeyModal();
                } else if (modalName.includes("auto") || modalName.includes("regra") || modalName.includes("rotina")) {
                    if (typeof openAutomationsModal === "function") openAutomationsModal(action.tab || "list");
                } else if (modalName.includes("camera") || modalName.includes("webcam") || modalName.includes("foto")) {
                    if (typeof openWebcamModal === "function") openWebcamModal();
                } else if (modalName.includes("comodo") || modalName.includes("cômodo") || modalName.includes("adicionar")) {
                    if (typeof openAddRoomModal === "function") openAddRoomModal();
                } else {
                    if (typeof openVoiceApiKeyModal === "function") openVoiceApiKeyModal();
                }
            } else if (verb.includes("close") || verb.includes("fechar")) {
                if (modalName.includes("auto") || modalName.includes("regra") || modalName.includes("rotina")) {
                    if (typeof closeAutomationsModal === "function") closeAutomationsModal();
                } else if (modalName.includes("chave") || modalName.includes("api") || modalName.includes("ia") || modalName.includes("config") || modalName.includes("voz") || modalName.includes("ajuste") || modalName.includes("conexao") || modalName.includes("conexão")) {
                    if (typeof closeVoiceApiKeyModal === "function") closeVoiceApiKeyModal();
                } else if (modalName.includes("guia") || modalName.includes("manual") || modalName.includes("ajuda")) {
                    if (typeof closeFeatureGuide === "function") closeFeatureGuide();
                } else if (modalName.includes("webcam") || modalName.includes("foto")) {
                    if (typeof closeWebcamModal === "function") closeWebcamModal();
                } else if (modalName.includes("comodo") || modalName.includes("cômodo") || modalName.includes("adicionar")) {
                    if (typeof closeAddRoomModal === "function") closeAddRoomModal();
                } else {
                    if (typeof closeFeatureGuide === "function") closeFeatureGuide();
                    if (typeof closeVoiceApiKeyModal === "function") closeVoiceApiKeyModal();
                    if (typeof closeAutomationsModal === "function") closeAutomationsModal();
                    if (typeof closeWebcamModal === "function") closeWebcamModal();
                    if (typeof closeAddRoomModal === "function") closeAddRoomModal();
                }
            }
            return true;
        }

        // 3. Controle de Dispositivos MQTT
        if (action.topic && action.state) {
            const statePayload = (action.state === "ON" || action.state === "on") ? "ON" : "OFF";
            if (mqttClient) {
                try {
                    mqttClient.publish(`pensador/casa/${action.topic}/set`, statePayload);
                } catch (e) { }
            }
            roomStates[action.topic] = (statePayload === "ON");
            renderScreenToastNotification({
                id: "mqtt_" + Date.now(),
                title: "⚡ Dispositivo Residencial",
                message: `Dispositivo '${action.topic}' alterado para ${statePayload}.`
            });
            return true;
        }

        return false;
    }

    // =========================================================================
    // SINCRONIZAÇÃO DE DADOS EM SEGUNDO PLANO (IA CONFIG & CASA CONFIG)
    // =========================================================================
    async function syncConfigsFromBackend() {
        const token = getAuthToken();
        if (!token) return;

        try {
            // AI Config
            const aiRes = await fetch("/api/user/ai-config", {
                headers: { "Authorization": `Bearer ${token}` }
            });
            if (aiRes.ok) {
                const aiData = await aiRes.json();
                if (aiData.agent_name) {
                    localStorage.setItem("smartHomeAgentName", aiData.agent_name);
                    const titleEl = document.getElementById("hudAgentTitle");
                    if (titleEl) titleEl.innerText = `Assistente ${aiData.agent_name}`;
                }
                if (aiData.voice) localStorage.setItem("smartHomeVoice", aiData.voice);
                if (aiData.ai_model) localStorage.setItem("smartHomeAiModel", aiData.ai_model);
                if (aiData.api_key) localStorage.setItem("geminiApiKey", aiData.api_key);
            }

            // House Config
            const houseRes = await fetch("/api/user/house-config", {
                headers: { "Authorization": `Bearer ${token}` }
            });
            if (houseRes.ok) {
                const houseData = await houseRes.json();
                cachedHouseConfig = houseData;
                localStorage.setItem("smartHomeConfig", JSON.stringify(houseData));
            }
        } catch (err) {
            console.warn("[VoiceAgent Config Sync]:", err);
        }
    }

    function startContinuousWatchdog() {
        if (watchdogInterval) clearInterval(watchdogInterval);
        watchdogInterval = setInterval(() => {
            if (alwaysListen && !isListening && !isSpeakingTTS && !isProcessingCommand && !isAudioPlayingActive && speechQueue.length === 0) {
                startVoiceRecognition();
            }
        }, 1200);
    }

    function checkAndPlayPendingSpeech() {
        try {
            const pending = sessionStorage.getItem("smartHomePendingSpeech") || localStorage.getItem("smartHomePendingSpeech");
            if (pending) {
                sessionStorage.removeItem("smartHomePendingSpeech");
                localStorage.removeItem("smartHomePendingSpeech");
                setTimeout(() => {
                    window.showVoiceHud();
                    setVoiceStatus("🤖", "Agente respondendo...", true);
                    showResponse(pending);
                    speakResponse(pending);
                }, 400);
            }
        } catch (e) { }
    }

    // =========================================================================
    // INICIALIZAÇÃO UNIVERSAL
    // =========================================================================
    function initUniversalVoiceAgent() {
        injectStylesAndUI();
        updateAlwaysListenUI();
        syncConfigsFromBackend();
        checkAndPlayPendingSpeech();

        ['click', 'touchstart', 'keydown'].forEach(evt => {
            document.addEventListener(evt, () => {
                primeAudioEngine();
                if (alwaysListen && !isListening && !isSpeakingTTS && !isProcessingCommand && !isAudioPlayingActive && speechQueue.length === 0) {
                    startVoiceRecognition();
                }
            }, { passive: true });
        });

        document.addEventListener("keydown", (e) => {
            if (e.key === "Escape") {
                if (isSpeakingTTS || isAudioPlayingActive || speechQueue.length > 0) {
                    silenciarAudio(true);
                }
            }
        });

        if (alwaysListen) {
            setTimeout(() => {
                startVoiceRecognition();
            }, 300);
            startContinuousWatchdog();
        }
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initUniversalVoiceAgent);
    } else {
        initUniversalVoiceAgent();
    }

})();

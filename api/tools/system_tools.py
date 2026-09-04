import os
import sys
import re
import glob
import uuid
import time
import signal
import shutil
import urllib.parse
import subprocess
from typing import Optional, Dict, Any, List
from langchain_core.tools import tool

try:
    from api.logger import agent_logger
except ImportError:
    try:
        from logger import agent_logger
    except ImportError:
        import logging
        agent_logger = logging.getLogger("AGENT")

try:
    from api.database import db_get_system_commands_flag
except ImportError:
    try:
        from database import db_get_system_commands_flag
    except ImportError:
        def db_get_system_commands_flag(email: str) -> bool:
            return False

# Contexto da sessão ativa
_ACTIVE_SYSTEM_USER: str = ""
_SYSTEM_COMMANDS_ENABLED_OVERRIDE: Optional[bool] = None


def set_system_tools_context(user_email: str = "", enabled: Optional[bool] = None):
    """Configura o contexto do usuário e flag de permissão de comandos do sistema."""
    global _ACTIVE_SYSTEM_USER, _SYSTEM_COMMANDS_ENABLED_OVERRIDE
    _ACTIVE_SYSTEM_USER = (user_email or "").strip().lower()
    _SYSTEM_COMMANDS_ENABLED_OVERRIDE = enabled
    agent_logger.info(f"[SystemTools] Contexto configurado para usuário: '{_ACTIVE_SYSTEM_USER}' (override: {enabled})")


def is_system_commands_allowed() -> bool:
    """Verifica se os comandos de sistema estão autorizados para o usuário ativo."""
    if _SYSTEM_COMMANDS_ENABLED_OVERRIDE is not None:
        return _SYSTEM_COMMANDS_ENABLED_OVERRIDE
    if _ACTIVE_SYSTEM_USER:
        try:
            return db_get_system_commands_flag(_ACTIVE_SYSTEM_USER)
        except Exception as e:
            agent_logger.warning(f"[SystemTools] Erro ao consultar flag no banco: {e}")
    return False


def _get_disabled_message() -> str:
    """Mensagem padrão quando a opção estiver desativada nas configurações."""
    return (
        "Os comandos de controle da máquina física (ajuste de volume, brilho da tela, abrir e fechar navegador) "
        "estão desativados nas configurações de segurança do sistema. "
        "Para permitir que o assistente execute essas ações, acesse o painel de Configurações e marque a opção 'Controle da Máquina Física'."
    )


def _get_session_env() -> Dict[str, str]:
    """Retorna variáveis de ambiente enriquecidas para comunicação com a sessão gráfica e D-Bus."""
    env = dict(os.environ)
    uid = str(os.getuid()) if hasattr(os, "getuid") else "1000"
    if "XDG_RUNTIME_DIR" not in env:
        env["XDG_RUNTIME_DIR"] = f"/run/user/{uid}"
    if "DBUS_SESSION_BUS_ADDRESS" not in env:
        env["DBUS_SESSION_BUS_ADDRESS"] = f"unix:path=/run/user/{uid}/bus"
    if "DISPLAY" not in env:
        env["DISPLAY"] = ":0"
    if "WAYLAND_DISPLAY" not in env and os.path.exists(f"/run/user/{uid}/wayland-0"):
        env["WAYLAND_DISPLAY"] = "wayland-0"
    return env


# =========================================================================
# FUNÇÕES DE CONTROLE DE VOLUME DO SISTEMA
# =========================================================================

def get_current_volume() -> int:
    """Obtém o volume atual da saída de áudio padrão (0 a 100%)."""
    env = _get_session_env()
    # 1. Tenta via pactl
    try:
        res = subprocess.run(["pactl", "get-sink-volume", "@DEFAULT_SINK@"], capture_output=True, text=True, timeout=3, env=env)
        if res.returncode == 0 and res.stdout:
            match = re.search(r'/\s*(\d+)%', res.stdout)
            if match:
                return int(match.group(1))
    except Exception:
        pass

    # 2. Tenta via wpctl
    try:
        res = subprocess.run(["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"], capture_output=True, text=True, timeout=3, env=env)
        if res.returncode == 0 and res.stdout:
            match = re.search(r'Volume:\s*([\d\.]+)', res.stdout)
            if match:
                return int(float(match.group(1)) * 100)
    except Exception:
        pass

    # 3. Tenta via amixer
    try:
        res = subprocess.run(["amixer", "sget", "Master"], capture_output=True, text=True, timeout=3, env=env)
        if res.returncode == 0 and res.stdout:
            match = re.search(r'\[(\d+)%\]', res.stdout)
            if match:
                return int(match.group(1))
    except Exception:
        pass

    return 50


def set_volume_level(level_pct: int) -> bool:
    """Define o volume do áudio para um valor percentual absoluto (0 a 100%)."""
    clamped = max(0, min(100, level_pct))
    env = _get_session_env()
    
    # 1. pactl
    try:
        res = subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{clamped}%"], capture_output=True, text=True, timeout=3, env=env)
        if res.returncode == 0:
            return True
    except Exception:
        pass

    # 2. wpctl
    try:
        res = subprocess.run(["wpctl", "set-volume", "@DEFAULT_AUDIO_SINK@", f"{clamped/100:.2f}"], capture_output=True, text=True, timeout=3, env=env)
        if res.returncode == 0:
            return True
    except Exception:
        pass

    # 3. amixer
    try:
        res = subprocess.run(["amixer", "sset", "Master", f"{clamped}%"], capture_output=True, text=True, timeout=3, env=env)
        if res.returncode == 0:
            return True
    except Exception:
        pass

    return False


def set_mute_state(mute: bool) -> bool:
    """Muta ou desmuta o áudio do sistema."""
    val_str = "1" if mute else "0"
    env = _get_session_env()
    try:
        res = subprocess.run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", val_str], capture_output=True, text=True, timeout=3, env=env)
        if res.returncode == 0:
            return True
    except Exception:
        pass

    try:
        res = subprocess.run(["amixer", "sset", "Master", "mute" if mute else "unmute"], capture_output=True, text=True, timeout=3, env=env)
        if res.returncode == 0:
            return True
    except Exception:
        pass

    return False


# =========================================================================
# FUNÇÕES DE CONTROLE DE BRILHO DA TELA (GNOME / WAYLAND / SYSFS / XRANDR)
# =========================================================================

def get_current_brightness() -> int:
    """Obtém o brilho atual da tela em porcentagem (0 a 100%)."""
    env = _get_session_env()

    # 1. Tenta via GNOME SettingsDaemon Power D-Bus (Wayland/GNOME nativo)
    try:
        res = subprocess.run([
            "gdbus", "call", "--session",
            "--dest", "org.gnome.SettingsDaemon.Power",
            "--object-path", "/org/gnome/SettingsDaemon/Power",
            "--method", "org.freedesktop.DBus.Properties.Get",
            "org.gnome.SettingsDaemon.Power.Screen", "Brightness"
        ], capture_output=True, text=True, timeout=3, env=env)
        if res.returncode == 0 and res.stdout:
            match = re.search(r'<(\d+)>', res.stdout)
            if match:
                return int(match.group(1))
    except Exception as e:
        agent_logger.warning(f"[SystemTools] Falha ao ler brilho via DBus: {e}")

    # 2. Tenta via /sys/class/backlight
    try:
        devices = glob.glob("/sys/class/backlight/*")
        if devices:
            dev = devices[0]
            with open(os.path.join(dev, "brightness")) as f:
                cur = int(f.read().strip())
            with open(os.path.join(dev, "max_brightness")) as f:
                mx = int(f.read().strip())
            if mx > 0:
                return int((cur / mx) * 100)
    except Exception:
        pass

    # 3. Tenta via brightnessctl
    try:
        res = subprocess.run(["brightnessctl", "get"], capture_output=True, text=True, timeout=3, env=env)
        res_max = subprocess.run(["brightnessctl", "max"], capture_output=True, text=True, timeout=3, env=env)
        if res.returncode == 0 and res_max.returncode == 0:
            cur = int(res.stdout.strip())
            mx = int(res_max.stdout.strip())
            if mx > 0:
                return int((cur / mx) * 100)
    except Exception:
        pass

    # 4. Fallback xrandr
    try:
        res = subprocess.run(["xrandr", "--verbose"], capture_output=True, text=True, timeout=3, env=env)
        if res.returncode == 0 and res.stdout:
            match = re.search(r'Brightness:\s*([\d\.]+)', res.stdout)
            if match:
                val = float(match.group(1))
                if val > 0:
                    return int(val * 100)
    except Exception:
        pass

    return 100


def set_screen_brightness(level_pct: int) -> bool:
    """Define o brilho da tela (0 a 100%) em GNOME, Wayland, Sysfs ou X11."""
    clamped_pct = max(5, min(100, level_pct))
    env = _get_session_env()
    success = False

    # 1. GNOME SettingsDaemon Power D-Bus (funciona diretamente no Wayland e Ubuntu GNOME)
    try:
        res = subprocess.run([
            "gdbus", "call", "--session",
            "--dest", "org.gnome.SettingsDaemon.Power",
            "--object-path", "/org/gnome/SettingsDaemon/Power",
            "--method", "org.freedesktop.DBus.Properties.Set",
            "org.gnome.SettingsDaemon.Power.Screen", "Brightness",
            f"<int32 {clamped_pct}>"
        ], capture_output=True, text=True, timeout=3, env=env)
        if res.returncode == 0:
            agent_logger.info(f"[SystemTools] Brilho ajustado via GNOME DBus para: {clamped_pct}%")
            success = True
    except Exception as e:
        agent_logger.warning(f"[SystemTools] Erro ao ajustar brilho via GNOME DBus: {e}")

    # 2. brightnessctl (fallback muito comum em Debian/Kali/Arch)
    try:
        res = subprocess.run(["brightnessctl", "set", f"{clamped_pct}%"], capture_output=True, text=True, timeout=3, env=env)
        if res.returncode == 0:
            agent_logger.info(f"[SystemTools] Brilho ajustado via brightnessctl para: {clamped_pct}%")
            return True
    except Exception:
        pass

    # 3. xbacklight (padrão em ambientes X11 e XFCE como Kali Linux)
    try:
        res = subprocess.run(["xbacklight", "-set", str(clamped_pct)], capture_output=True, text=True, timeout=3, env=env)
        if res.returncode == 0:
            agent_logger.info(f"[SystemTools] Brilho ajustado via xbacklight para: {clamped_pct}%")
            return True
    except Exception:
        pass

    # 4. Escrita direta em /sys/class/backlight
    try:
        devices = glob.glob("/sys/class/backlight/*")
        if devices:
            dev = devices[0]
            with open(os.path.join(dev, "max_brightness")) as f:
                mx = int(f.read().strip())
            if mx > 0:
                target_val = int((clamped_pct / 100.0) * mx)
                with open(os.path.join(dev, "brightness"), "w") as f:
                    f.write(str(target_val))
                agent_logger.info(f"[SystemTools] Brilho ajustado via /sys/class/backlight para: {clamped_pct}%")
                return True
    except Exception:
        pass

    # 5. xrandr (fallback para sessões X11 ou monitores externos)
    try:
        level_float = round(clamped_pct / 100.0, 2)
        res = subprocess.run(["xrandr", "-q"], capture_output=True, text=True, timeout=3, env=env)
        if res.returncode == 0:
            screens = re.findall(r'^(\S+)\s+connected', res.stdout, re.MULTILINE)
            for sc in screens:
                subprocess.run(["xrandr", "--output", sc, "--brightness", str(level_float)], capture_output=True, text=True, timeout=3, env=env)
            agent_logger.info(f"[SystemTools] Brilho ajustado via xrandr para: {level_float}")
            return True
    except Exception:
        pass

    return success


# =========================================================================
# GERENCIADOR DE JANELAS E PÁGINAS DO NAVEGADOR
# =========================================================================

class BrowserWindowManager:
    """Gerencia instâncias isoladas de janelas do navegador abertas pelo assistente."""
    _instance: Optional['BrowserWindowManager'] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(BrowserWindowManager, cls).__new__(cls)
            cls._instance.windows = []
        return cls._instance

    def _resolve_url_and_label(self, site_ou_pesquisa: str) -> tuple[str, str]:
        query = (site_ou_pesquisa or "").strip()
        if not query or query.lower() in ["navegador", "browser", "internet", "google", "abrir"]:
            return "https://www.google.com", "a página inicial do Google"
        elif query.startswith("http://") or query.startswith("https://"):
            return query, query
        elif "." in query and " " not in query:
            return f"https://{query}", query
        else:
            return f"https://www.google.com/search?q={urllib.parse.quote(query)}", f"a pesquisa por '{query}'"

    def open_page(self, site_ou_pesquisa: str = "") -> str:
        """Abre uma nova janela de navegador isolada e controlável."""
        target_url, label = self._resolve_url_and_label(site_ou_pesquisa)
        u_id = uuid.uuid4().hex[:6]
        profile_dir = f"/tmp/assistant_browser_{u_id}"
        env = _get_session_env()

        # Proteção: nunca tenta abrir a si próprio em loop
        agent_logger.info(f"[SystemTools] Abrindo janela de navegador: '{target_url}' (ID: {u_id})")

        try:
            proc = subprocess.Popen(
                [
                    "google-chrome",
                    f"--user-data-dir={profile_dir}",
                    "--new-window",
                    "--no-first-run",
                    "--no-default-browser-check",
                    target_url
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
                env=env
            )

            # Registra janela aberta
            entry = {
                "id": u_id,
                "proc": proc,
                "url": target_url,
                "label": label,
                "profile_dir": profile_dir,
                "time": time.time()
            }
            self.windows.append(entry)
            return f"Navegador aberto com sucesso em {label}."

        except Exception as err_chrome:
            agent_logger.warning(f"[SystemTools] Falha ao abrir via google-chrome: {err_chrome}. Tentando xdg-open.")
            try:
                proc = subprocess.Popen(
                    ["xdg-open", target_url],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                    env=env
                )
                entry = {
                    "id": u_id,
                    "proc": proc,
                    "url": target_url,
                    "label": label,
                    "profile_dir": profile_dir,
                    "time": time.time()
                }
                self.windows.append(entry)
                return f"Navegador aberto com sucesso em {label}."
            except Exception as err_xdg:
                return f"Erro ao tentar abrir o navegador: {err_xdg}"

    def close_page(self, site_ou_alvo: str = "") -> str:
        """Fecha páginas abertas pelo assistente, protegendo rigorosamente a tela do sistema."""
        target_clean = (site_ou_alvo or "").lower().strip()

        # Atualiza lista de janelas ativas
        alive = [w for w in self.windows if w["proc"].poll() is None]
        self.windows = alive

        if not alive:
            return "Nenhuma página ou janela aberta pelo assistente está em execução no momento."

        to_close = []

        # 1. Se informou um alvo específico (ex: "youtube", "google", "globo")
        if target_clean and target_clean not in ["navegador", "pagina", "página", "aba", "janela", "tudo", "fechar", "fecha"]:
            for w in reversed(alive):
                url_low = w["url"].lower()
                label_low = w["label"].lower()
                if target_clean in url_low or target_clean in label_low:
                    to_close.append(w)
                    break

        # 2. Se for para fechar tudo aberto pelo assistente
        if not to_close and any(w in target_clean for w in ["tudo", "todas", "todos"]):
            to_close.extend(alive)

        # 3. Fallback: fecha a última janela que o assistente abriu
        if not to_close:
            to_close.append(alive[-1])

        closed_labels = []
        for w in to_close:
            # Proteção estrita: nunca fecha páginas locais da casa inteligente
            if any(prot in w["url"].lower() for prot in ["localhost", "127.0.0.1", "casa", "smarthome"]):
                continue

            try:
                if w["proc"].poll() is None:
                    os.killpg(os.getpgid(w["proc"].pid), signal.SIGTERM)
                    try:
                        w["proc"].wait(timeout=1.5)
                    except Exception:
                        os.killpg(os.getpgid(w["proc"].pid), signal.SIGKILL)
            except Exception as e:
                agent_logger.warning(f"[SystemTools] Aviso ao fechar janela PID {w['proc'].pid}: {e}")

            # Limpa profile temporário
            try:
                shutil.rmtree(w["profile_dir"], ignore_errors=True)
            except Exception:
                pass

            if w in self.windows:
                self.windows.remove(w)
            closed_labels.append(w["label"])

        if closed_labels:
            if len(closed_labels) == 1:
                return f"A página de {closed_labels[0]} foi fechada com sucesso."
            else:
                return f"As seguintes páginas foram fechadas com sucesso: {', '.join(closed_labels)}."
        else:
            return "Nenhuma página correspondente pôde ser fechada."


_browser_mgr = BrowserWindowManager()


# =========================================================================
# FERRAMENTAS LANGCHAIN
# =========================================================================

@tool
def controlar_volume_sistema(comando: str) -> str:
    """
    Controla o volume do áudio do computador / máquina física.
    Permite aumentar o volume, abaixar o volume, definir um valor em porcentagem (ex: '50%', '80%', '100%'),
    mutar, desmutar ou verificar o volume atual.
    
    Use SEMPRE que o usuário pedir:
    - 'aumenta o volume', 'aumentar o som', 'aumenta em 10%', 'aumenta um pouco o volume'.
    - 'abaixa o volume', 'diminui o som', 'abaixar o volume', 'abaixa em 20%'.
    - 'coloca o volume em 70%', 'volume em 50%', 'volume no máximo', 'volume no mínimo'.
    - 'muta o som', 'coloca no mudo', 'desmuta', 'tira do mudo'.
    - 'qual é o volume atual?', 'como está o som?'.
    
    Args:
        comando: Ação a ser executada ('aumentar', 'abaixar', '50%', 'mutar', 'desmutar', 'status', etc.).
    """
    if not is_system_commands_allowed():
        return _get_disabled_message()

    raw = (comando or "").strip().lower()
    current = get_current_volume()
    agent_logger.info(f"[SystemTools] Comando de volume recebido: '{raw}' | Volume atual: {current}%")

    # 1. Mutar
    if any(w in raw for w in ["mudo", "mutar", "silenciar", "mute"]):
        set_mute_state(True)
        return "Áudio do computador colocado no mudo."

    # 2. Desmutar
    if any(w in raw for w in ["desmutar", "desmuta", "tirar do mudo", "tira do mudo", "unmute"]):
        set_mute_state(False)
        return f"Áudio do computador desmutado. Volume atual em {current}%."

    # 3. Status
    if any(w in raw for w in ["status", "qual", "quanto", "nivel", "verificar", "consultar"]) and not any(w in raw for w in ["aument", "abaix", "diminu"]):
        return f"O volume atual do computador está em {current}%."

    # 4. Máximo / Mínimo
    if "maximo" in raw or "máximo" in raw or "100" in raw:
        set_volume_level(100)
        return "Volume do computador ajustado para o nível máximo (100%)."
    if "minimo" in raw or "mínimo" in raw or "zero" in raw:
        set_volume_level(10)
        return "Volume do computador ajustado para o nível mínimo (10%)."

    # 5. Valor numérico explícito (ex: "70%", "volume em 80")
    num_match = re.search(r'(\d+)\s*%?', raw)
    if num_match and not any(w in raw for w in ["aument", "abaix", "diminu", "mais", "menos"]):
        target_vol = int(num_match.group(1))
        set_volume_level(target_vol)
        return f"Volume do computador ajustado para {target_vol}%."

    # 6. Aumentar volume
    if any(w in raw for w in ["aument", "subir", "mais", "alto"]):
        step = 10
        if num_match:
            step = int(num_match.group(1))
        new_vol = min(100, current + step)
        set_volume_level(new_vol)
        return f"Volume aumentado para {new_vol}%."

    # 7. Abaixar volume
    if any(w in raw for w in ["abaix", "diminu", "baixar", "menos", "baixo"]):
        step = 10
        if num_match:
            step = int(num_match.group(1))
        new_vol = max(0, current - step)
        set_volume_level(new_vol)
        return f"Volume diminuído para {new_vol}%."

    # Fallback
    if num_match:
        target_vol = int(num_match.group(1))
        set_volume_level(target_vol)
        return f"Volume ajustado para {target_vol}%."

    new_vol = min(100, current + 10)
    set_volume_level(new_vol)
    return f"Volume ajustado para {new_vol}%."


@tool
def controlar_brilho_tela(comando: str) -> str:
    """
    Controla o nível de brilho da tela / monitores do computador / máquina física.
    Permite aumentar o brilho, abaixar o brilho, definir um valor em porcentagem (ex: '80%', '50%', '100%')
    ou consultar o brilho atual da tela.
    
    Use SEMPRE que o usuário pedir:
    - 'aumenta o brilho', 'aumentar o brilho da tela', 'deixa a tela mais clara', 'aumenta o brilho em 15%'.
    - 'abaixa o brilho', 'diminui o brilho da tela', 'deixa a tela mais escura', 'abaixar o brilho'.
    - 'coloca o brilho em 80%', 'brilho da tela em 50%', 'brilho no máximo', 'brilho no mínimo'.
    - 'qual é o brilho da tela?', 'como está o brilho?'.
    
    Args:
        comando: Ação a ser executada ('aumentar', 'abaixar', '80%', 'maximo', 'minimo', 'status', etc.).
    """
    if not is_system_commands_allowed():
        return _get_disabled_message()

    raw = (comando or "").strip().lower()
    current = get_current_brightness()
    agent_logger.info(f"[SystemTools] Comando de brilho recebido: '{raw}' | Brilho atual: {current}%")

    # 1. Status
    if any(w in raw for w in ["status", "qual", "quanto", "nivel", "verificar", "consultar"]) and not any(w in raw for w in ["aument", "abaix", "diminu"]):
        return f"O brilho atual da tela está em {current}%."

    # 2. Máximo / Mínimo
    if "maximo" in raw or "máximo" in raw or "100" in raw:
        set_screen_brightness(100)
        return "Brilho da tela ajustado para 100%."
    if "minimo" in raw or "mínimo" in raw or "escuro" in raw:
        set_screen_brightness(20)
        return "Brilho da tela ajustado para o nível mínimo (20%)."

    # 3. Valor numérico explícito (ex: "80%", "brilho em 50")
    num_match = re.search(r'(\d+)\s*%?', raw)
    if num_match and not any(w in raw for w in ["aument", "abaix", "diminu", "mais", "menos", "clara", "escura"]):
        target_br = int(num_match.group(1))
        set_screen_brightness(target_br)
        return f"Brilho da tela ajustado para {target_br}%."

    # 4. Aumentar brilho
    if any(w in raw for w in ["aument", "subir", "mais", "clara", "claro"]):
        step = 15
        if num_match:
            step = int(num_match.group(1))
        new_br = min(100, current + step)
        set_screen_brightness(new_br)
        return f"Brilho da tela aumentado para {new_br}%."

    # 5. Abaixar brilho
    if any(w in raw for w in ["abaix", "diminu", "baixar", "menos", "escura", "escuro"]):
        step = 15
        if num_match:
            step = int(num_match.group(1))
        new_br = max(10, current - step)
        set_screen_brightness(new_br)
        return f"Brilho da tela diminuído para {new_br}%."

    # Fallback
    if num_match:
        target_br = int(num_match.group(1))
        set_screen_brightness(target_br)
        return f"Brilho da tela ajustado para {target_br}%."

    new_br = min(100, current + 15)
    set_screen_brightness(new_br)
    return f"Brilho da tela ajustado para {new_br}%."


@tool
def abrir_navegador_sistema(site_ou_pesquisa: Optional[str] = "") -> str:
    """
    Abre o navegador de internet (Google Chrome / Firefox) diretamente na máquina física.
    Pode abrir a página inicial padrão, um site informado (ex: 'youtube.com', 'google.com', 'github.com')
    ou realizar uma pesquisa no Google.
    
    Use SEMPRE que o usuário pedir:
    - 'abre o navegador', 'abrir o navegador', 'abre a internet', 'inicia o navegador'.
    - 'abre o YouTube no navegador', 'abre o site do Google', 'abre o GitHub no navegador'.
    - 'pesquisa receitas de bolo no navegador', 'abre o navegador pesquisando notícias'.
    
    Args:
        site_ou_pesquisa: Site, URL ou termo de pesquisa que o usuário deseja abrir no navegador (opcional).
    """
    if not is_system_commands_allowed():
        return _get_disabled_message()

    agent_logger.info(f"[SystemTools] Abrindo navegador para: '{site_ou_pesquisa}'")
    return _browser_mgr.open_page(site_ou_pesquisa or "")


@tool
def fechar_navegador_sistema(site_ou_alvo: Optional[str] = "") -> str:
    """
    Fecha páginas, abas ou janelas do navegador de internet que foram abertas pelo assistente.
    Pode fechar uma página específica (ex: 'fecha o YouTube', 'fecha o Google', 'fecha a página')
    ou fechar todas as páginas abertas pelo assistente.
    
    Por segurança, esta ferramenta NUNCA fecha a página principal da casa inteligente / assistente.
    
    Use SEMPRE que o usuário pedir:
    - 'fecha a página', 'fecha o navegador', 'fecha a janela', 'fecha a aba'.
    - 'fecha o YouTube', 'fecha o Google', 'fecha a página do YouTube'.
    - 'fecha todas as páginas do navegador', 'fecha tudo o que você abriu'.
    
    Args:
        site_ou_alvo: Nome do site ou termo da página a ser fechada (opcional). Deixe vazio para fechar a última janela aberta.
    """
    if not is_system_commands_allowed():
        return _get_disabled_message()

    agent_logger.info(f"[SystemTools] Fechando navegador para alvo: '{site_ou_alvo}'")
    return _browser_mgr.close_page(site_ou_alvo or "")

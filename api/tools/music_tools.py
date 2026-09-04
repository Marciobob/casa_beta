import os
import sys
import re
import json
import time
import signal
import shutil
import subprocess
import threading
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
    from api.tools.youtube_tools import search_youtube_videos, extract_video_id
except ImportError:
    try:
        from tools.youtube_tools import search_youtube_videos, extract_video_id
    except ImportError:
        search_youtube_videos = None
        extract_video_id = None

try:
    import yt_dlp
except ImportError:
    yt_dlp = None


class MusicPlayerManager:
    """Gerenciador Singleton thread-safe de reprodução de áudio em segundo plano."""
    _instance: Optional['MusicPlayerManager'] = None
    _global_lock = threading.RLock()

    def __new__(cls):
        with cls._global_lock:
            if cls._instance is None:
                cls._instance = super(MusicPlayerManager, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return
        self._lock = threading.RLock()
        self._process: Optional[subprocess.Popen] = None
        self._current_track: Optional[Dict[str, Any]] = None
        self._start_time: Optional[float] = None
        self._initialized = True

    def _kill_ffplay_system_processes(self) -> bool:
        """Encerra com segurança qualquer processo ffplay ou mpv rodando áudio no sistema."""
        killed_any = False
        try:
            # Verifica se há processos ffplay rodando
            check = subprocess.run(["pgrep", "ffplay"], capture_output=True, text=True, timeout=2)
            if check.returncode == 0 and check.stdout.strip():
                pids = check.stdout.strip().split()
                agent_logger.info(f"[MusicPlayer] Finalizando processos ffplay do sistema: {pids}")
                subprocess.run(["pkill", "-15", "-f", "ffplay.*-nodisp"], capture_output=True, timeout=2)
                subprocess.run(["pkill", "-15", "ffplay"], capture_output=True, timeout=2)
                time.sleep(0.3)
                # Força SIGKILL se ainda houver algum
                subprocess.run(["pkill", "-9", "-f", "ffplay.*-nodisp"], capture_output=True, timeout=2)
                subprocess.run(["pkill", "-9", "ffplay"], capture_output=True, timeout=2)
                killed_any = True
        except Exception as e:
            agent_logger.warning(f"[MusicPlayer] Erro ao encerrar processos ffplay via pkill: {e}")
            
        try:
            check_mpv = subprocess.run(["pgrep", "-f", "mpv.*--no-video"], capture_output=True, text=True, timeout=2)
            if check_mpv.returncode == 0 and check_mpv.stdout.strip():
                subprocess.run(["pkill", "-9", "-f", "mpv.*--no-video"], capture_output=True, timeout=2)
                killed_any = True
        except Exception:
            pass

        return killed_any

    def stop(self) -> bool:
        """Interrompe qualquer reprodução ativa de forma limpa e imediata."""
        with self._lock:
            was_playing = False
            
            # 1. Se temos o processo rastreado em memória
            if self._process is not None:
                try:
                    if self._process.poll() is None:
                        agent_logger.info(f"[MusicPlayer] Finalizando processo rastreado PID: {self._process.pid}")
                        try:
                            os.killpg(os.getpgid(self._process.pid), signal.SIGTERM)
                            self._process.wait(timeout=1.0)
                        except (subprocess.TimeoutExpired, ProcessLookupError, Exception):
                            try:
                                os.killpg(os.getpgid(self._process.pid), signal.SIGKILL)
                            except Exception:
                                pass
                        try:
                            self._process.terminate()
                            self._process.kill()
                        except Exception:
                            pass
                        was_playing = True
                except Exception as e:
                    agent_logger.warning(f"[MusicPlayer] Aviso ao finalizar processo: {e}")
                finally:
                    self._process = None

            # 2. Garante que qualquer outro processo de áudio em segundo plano também seja encerrado
            killed_system = self._kill_ffplay_system_processes()
            if killed_system:
                was_playing = True

            self._current_track = None
            self._start_time = None
            return was_playing

    def is_playing(self) -> bool:
        """Verifica se há áudio sendo reproduzido no momento."""
        with self._lock:
            if self._process is not None and self._process.poll() is None:
                return True
            # Verifica se há ffplay rodando no sistema
            try:
                check = subprocess.run(["pgrep", "ffplay"], capture_output=True, text=True, timeout=2)
                if check.returncode == 0 and check.stdout.strip():
                    return True
            except Exception:
                pass
            return False

    def get_status(self) -> Dict[str, Any]:
        """Retorna o status detalhado da reprodução atual."""
        with self._lock:
            if self.is_playing():
                if self._current_track:
                    elapsed_sec = int(time.time() - (self._start_time or time.time()))
                    mins, secs = divmod(elapsed_sec, 60)
                    elapsed_str = f"{mins}m {secs:02d}s" if mins > 0 else f"{secs}s"
                    return {
                        "playing": True,
                        "title": self._current_track.get("title", "Áudio do YouTube"),
                        "channel": self._current_track.get("channel", "YouTube"),
                        "duration": self._current_track.get("duration_str", ""),
                        "url": self._current_track.get("webpage_url", ""),
                        "elapsed": elapsed_str,
                        "message": f"Reproduzindo '{self._current_track.get('title')}' ({elapsed_str} decorridos)."
                    }
                else:
                    return {
                        "playing": True,
                        "message": "Há uma música ou áudio em reprodução nos alto-falantes."
                    }
            
            # Limpa caso tenha encerrado
            self._process = None
            self._current_track = None
            self._start_time = None
            return {
                "playing": False,
                "message": "Nenhuma música está tocando no momento."
            }

    def _monitor_proc(self, proc: subprocess.Popen, track_title: str):
        """Thread em segundo plano que detecta o término natural da música."""
        try:
            proc.wait()
        except Exception:
            pass
        with self._lock:
            if self._process == proc:
                agent_logger.info(f"[MusicPlayer] Reprodução de '{track_title}' finalizada naturalmente.")
                self._process = None
                self._current_track = None
                self._start_time = None

    def _extract_stream_info(self, target_url: str) -> Optional[Dict[str, Any]]:
        """Extrai URL direta do stream de áudio com yt_dlp (módulo Python ou CLI)."""
        # 1. Tenta via biblioteca Python yt_dlp se disponível
        if yt_dlp is not None:
            ydl_opts = {
                'format': 'bestaudio/best',
                'noplaylist': True,
                'quiet': True,
                'no_warnings': True,
                'socket_timeout': 10,
                'ignoreerrors': True
            }
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(target_url, download=False)
                    if info:
                        entries = info.get('entries', []) if 'entries' in info else [info]
                        for entry in entries:
                            if entry and entry.get('url'):
                                duration_sec = entry.get('duration') or 0
                                dur_mins, dur_secs = divmod(int(duration_sec), 60)
                                dur_str = f"{dur_mins}:{dur_secs:02d}" if duration_sec else ""

                                return {
                                    "title": entry.get("title") or "Música",
                                    "channel": entry.get("uploader") or entry.get("channel") or "YouTube",
                                    "duration_sec": duration_sec,
                                    "duration_str": dur_str,
                                    "stream_url": entry.get("url"),
                                    "webpage_url": entry.get("webpage_url") or target_url
                                }
            except Exception as e:
                agent_logger.warning(f"[MusicPlayer] Falha via yt_dlp python para '{target_url}': {e}")

        # 2. Fallback via CLI executável yt-dlp
        yt_bin = shutil.which("yt-dlp") or "/home/marcio/.local/bin/yt-dlp"
        if os.path.exists(yt_bin) or shutil.which("yt-dlp"):
            try:
                cmd = [yt_bin, "-J", "-f", "bestaudio/best", "--no-playlist", "--no-warnings", target_url]
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=12)
                if res.returncode == 0 and res.stdout.strip():
                    info = json.loads(res.stdout)
                    entries = info.get('entries', []) if 'entries' in info else [info]
                    for entry in entries:
                        stream_url = entry.get('url')
                        # Se não achou na raiz, procura nos formats
                        if not stream_url and 'formats' in entry:
                            audio_formats = [f for f in entry['formats'] if f.get('acodec') != 'none' and f.get('url')]
                            if audio_formats:
                                stream_url = audio_formats[-1].get('url')
                        
                        if stream_url:
                            duration_sec = entry.get('duration') or 0
                            dur_mins, dur_secs = divmod(int(duration_sec), 60)
                            dur_str = f"{dur_mins}:{dur_secs:02d}" if duration_sec else ""
                            return {
                                "title": entry.get("title") or "Música",
                                "channel": entry.get("uploader") or entry.get("channel") or "YouTube",
                                "duration_sec": duration_sec,
                                "duration_str": dur_str,
                                "stream_url": stream_url,
                                "webpage_url": entry.get("webpage_url") or target_url
                            }
            except Exception as err_cli:
                agent_logger.warning(f"[MusicPlayer] Falha via CLI yt-dlp para '{target_url}': {err_cli}")

        return None

    def play(self, query_or_url: str) -> Dict[str, Any]:
        """Busca e inicia a reprodução do áudio em segundo plano."""
        clean_query = (query_or_url or "").strip()
        if not clean_query:
            return {"success": False, "message": "Nenhum termo ou link de música foi informado."}

        # 1. Interrompe qualquer reprodução anterior antes de começar a nova
        self.stop()

        agent_logger.info(f"[MusicPlayer] Iniciando busca e reprodução para: '{clean_query}'")

        # 2. Verifica se é link direto ou ID de vídeo
        vid_id = extract_video_id(clean_query) if extract_video_id else None
        track_info = None

        if vid_id:
            direct_url = f"https://www.youtube.com/watch?v={vid_id}"
            track_info = self._extract_stream_info(direct_url)
        elif clean_query.startswith("http://") or clean_query.startswith("https://"):
            track_info = self._extract_stream_info(clean_query)
        else:
            # 3. Pesquisa rápida no YouTube
            candidates = []
            if search_youtube_videos:
                try:
                    candidates = search_youtube_videos(clean_query, max_results=3)
                except Exception as e:
                    agent_logger.warning(f"[MusicPlayer] Falha na busca rápida: {e}")

            # Itera sobre os candidatos até achar um com stream funcional
            if candidates:
                for cand in candidates:
                    cand_url = cand.get("url")
                    if cand_url:
                        track_info = self._extract_stream_info(cand_url)
                        if track_info:
                            break

            # Fallback usando busca interna do yt_dlp
            if not track_info:
                track_info = self._extract_stream_info(f"ytsearch3:{clean_query}")

        if not track_info or not track_info.get("stream_url"):
            return {
                "success": False,
                "message": f"Não foi possível encontrar ou carregar o áudio de '{clean_query}' no YouTube."
            }

        stream_url = track_info["stream_url"]

        # 4. Inicia processo de reprodução via ffplay
        try:
            proc = subprocess.Popen(
                ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", stream_url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )

            # Aguarda uma fração de segundo para certificar que o processo inicializou
            time.sleep(0.4)
            if proc.poll() is not None:
                return {
                    "success": False,
                    "message": "Erro ao iniciar o player de áudio do sistema."
                }

            with self._lock:
                self._process = proc
                self._current_track = track_info
                self._start_time = time.time()

            # Thread monitora para limpar quando o áudio acabar
            mon_thread = threading.Thread(
                target=self._monitor_proc,
                args=(proc, track_info.get("title", "")),
                daemon=True
            )
            mon_thread.start()

            title = track_info.get("title")
            channel = track_info.get("channel")
            dur = f" ({track_info.get('duration_str')})" if track_info.get('duration_str') else ""

            agent_logger.info(f"[MusicPlayer] Reprodução iniciada com sucesso: '{title}' por '{channel}' (PID {proc.pid})")

            return {
                "success": True,
                "title": title,
                "channel": channel,
                "duration": track_info.get("duration_str"),
                "url": track_info.get("webpage_url"),
                "message": f"Iniciando a reprodução de '{title}' de {channel}{dur} nos alto-falantes."
            }

        except Exception as e:
            agent_logger.error(f"[MusicPlayer] Falha ao executar player de áudio: {e}")
            return {
                "success": False,
                "message": f"Ocorreu um erro ao tocar o áudio: {str(e)}"
            }


# Instância global do player de música
_player = MusicPlayerManager()


@tool
def tocar_musica(termo_ou_musica: str) -> str:
    """
    Busca e toca músicas, gêneros musicais (ex: samba, pagode, rock, sertanejo, etc.), 
    podcasts, faixas de artistas ou o áudio de vídeos do YouTube diretamente nos alto-falantes 
    do sistema em segundo plano.
    
    Use SEMPRE que o usuário pedir:
    - Tocar uma música, artista ou banda (ex: 'toca Gusttavo Lima', 'coloque Queen', 'toca Evidências').
    - Escutar um gênero musical (ex: 'quero escutar um samba', 'toca um pagode', 'coloque um jazz relaxante', 'toca um sertanejo').
    - Tocar um podcast ou programa (ex: 'coloque o podcast do Flow', 'toca o podcast Podpah').
    - Tocar um link ou vídeo específico do YouTube para ouvir.
    
    Args:
        termo_ou_musica: Nome da música, artista, gênero musical (samba, pagode, etc.), podcast ou link do YouTube.
    """
    if not termo_ou_musica or not termo_ou_musica.strip():
        return "Por favor, informe qual música, gênero musical, artista ou podcast você deseja escutar."

    res = _player.play(termo_ou_musica.strip())
    if res.get("success"):
        return res.get("message", "A música começou a tocar.")
    else:
        return f"Erro: {res.get('message', 'Não foi possível iniciar a reprodução da música.')}"


@tool
def parar_musica() -> str:
    """
    Para e interrompe imediatamente a reprodução de qualquer música, podcast ou áudio do YouTube 
    que esteja tocando nos alto-falantes do sistema.
    
    Use SEMPRE que o usuário pedir:
    - 'para a música', 'pare a música', 'desliga o som', 'para o áudio', 'silêncio', 'chega de música'.
    - Interromper, pausar ou desligar qualquer som que esteja em execução.
    """
    stopped = _player.stop()
    if stopped:
        return "A reprodução de áudio foi interrompida com sucesso."
    else:
        return "Nenhuma música está tocando no momento."


@tool
def status_musica() -> str:
    """
    Informa qual música, podcast ou áudio do YouTube está tocando no momento e o tempo decorrido.
    
    Use quando o usuário perguntar:
    - 'qual música está tocando?', 'o que está tocando agora?', 'qual o som atual?'.
    """
    status = _player.get_status()
    return status.get("message", "Nenhuma música está tocando no momento.")

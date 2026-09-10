import os
import time
import json
import threading
import requests
from datetime import datetime, timedelta, timezone, date
from typing import Optional, Dict, Any, List, Tuple
import dateutil.tz

try:
    from api.logger import system_logger, vision_logger
    from api.database import (
        db_get_all_active_automations,
        db_get_automation_by_id,
        db_record_automation_run,
        db_is_event_already_notified,
        db_mark_event_notified,
        db_get_google_credentials,
        db_get_telegram_config,
        db_get_slack_config,
        db_get_ai_config,
        db_get_camera_config,
        db_get_user_cameras,
        db_add_screen_notification,
        get_user_profile,
        db_get_tasks
    )
    from api.telegram_bot import send_telegram_message, send_telegram_photo
    from api.tools.slack_tools import (
        send_slack_message_payload,
        build_slack_report_blocks,
        _resolve_channel_id,
        _resolve_user_name,
        _format_slack_text
    )
    from api.tools.calendar_tools import (
        connect_caldav, 
        formatar_evento, 
        set_calendar_credentials_context
    )
    from api.tools.mqtt_tools import controlar_luzes, relatorio_status_casa
    from api.tools.gmail_tools import set_gmail_credentials_context, ler_emails_recentes
    from api.tools.vision_tools import capture_camera_frame
    from api.video_automation import evaluate_video_automation, clear_video_cooldown, opencv_detect_person_or_face
except ImportError:
    from logger import system_logger, vision_logger
    from database import (
        db_get_all_active_automations,
        db_get_automation_by_id,
        db_record_automation_run,
        db_is_event_already_notified,
        db_mark_event_notified,
        db_get_google_credentials,
        db_get_telegram_config,
        db_get_slack_config,
        db_get_ai_config,
        db_get_camera_config,
        db_get_user_cameras,
        db_add_screen_notification,
        get_user_profile,
        db_get_tasks
    )
    from telegram_bot import send_telegram_message, send_telegram_photo
    from tools.slack_tools import (
        send_slack_message_payload,
        build_slack_report_blocks,
        _resolve_channel_id,
        _resolve_user_name,
        _format_slack_text
    )
    from tools.calendar_tools import (
        connect_caldav, 
        formatar_evento, 
        set_calendar_credentials_context
    )
    from tools.mqtt_tools import controlar_luzes, relatorio_status_casa
    from tools.gmail_tools import set_gmail_credentials_context, ler_emails_recentes
    from tools.vision_tools import capture_camera_frame
    from video_automation import evaluate_video_automation, clear_video_cooldown, opencv_detect_person_or_face


class AutomationEngine:
    """Motor de execução periódica de automações em segundo plano."""

    def __init__(self, check_interval_seconds: int = 30):
        self.check_interval = check_interval_seconds
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

    def start(self):
        """Inicia a thread do motor em segundo plano."""
        with self._lock:
            if self._running:
                return
            self._running = True
            self._thread = threading.Thread(
                target=self._worker_loop,
                name="AutomationEngineWorker",
                daemon=True
            )
            self._thread.start()
            system_logger.info("⚡ Motor de Automações em 2º Plano (AutomationEngine) iniciado.")

    def stop(self):
        """Para o motor de automações."""
        with self._lock:
            self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
            system_logger.info("⚡ Motor de Automações em 2º Plano finalizado.")

    def is_running(self) -> bool:
        return self._running

    def _worker_loop(self):
        """Loop contínuo de verificação das automações."""
        while self._running:
            try:
                self._tick()
            except Exception as e:
                system_logger.error(f"Erro no ciclo do AutomationEngine: {e}")
            time.sleep(self.check_interval)

    def _tick(self):
        """Verifica todas as automações ativas no banco de dados."""
        active_rules = db_get_all_active_automations()
        if not active_rules:
            return

        tz_local = dateutil.tz.tzlocal()
        now_local = datetime.now(tz_local)
        current_hm = now_local.strftime("%H:%M")

        for rule in active_rules:
            try:
                self._process_rule(rule, now_local, current_hm)
            except Exception as e_rule:
                system_logger.error(f"Erro ao processar regra '{rule.get('name')}' (ID {rule.get('id')}): {e_rule}")

    def _process_rule(self, rule: Dict[str, Any], now_local: datetime, current_hm: str):
        auto_id = rule["id"]
        user_email = rule["user_email"]
        auto_type = rule.get("automation_type", "")
        trigger_type = rule.get("trigger_type", "")
        trigger_val = str(rule.get("trigger_value", "")).strip()
        action_type = rule.get("action_type", "")
        payload = rule.get("action_payload", {}) or {}

        # 1. Automação de Lembretes de Agenda & Tarefas (relativo a eventos)
        if auto_type == "calendar_reminder":
            self.execute_calendar_reminder(rule, now_local)
            return

        # 2. Automações disparadas em horário diário fixo (ex: "08:00" ou "18:30")
        if trigger_type == "daily_time":
            if trigger_val == current_hm:
                today_str = now_local.strftime("%Y-%m-%d")
                event_key = f"daily_{auto_id}_{today_str}_{current_hm}"
                if not db_is_event_already_notified(auto_id, event_key):
                    self.execute_automation_action(rule, is_manual=False)
                    db_mark_event_notified(auto_id, user_email, event_key)
            return

        # 3. Automações por intervalo de minutos
        if trigger_type == "interval_minutes":
            try:
                interval_mins = int(trigger_val)
            except ValueError:
                interval_mins = 60
            
            last_run = rule.get("last_run_at")
            should_run = False
            if not last_run:
                should_run = True
            else:
                try:
                    last_dt = datetime.fromisoformat(last_run.replace("Z", "+00:00"))
                    diff = (datetime.now(timezone.utc) - last_dt).total_seconds() / 60.0
                    if diff >= interval_mins:
                        should_run = True
                except Exception:
                    should_run = True

            if should_run:
                self.execute_automation_action(rule, is_manual=False)
            return

        # 4. Automações de Vídeo & Visão Computacional (Reconhecimento Facial / Detecção)
        if auto_type.startswith("video_") or action_type == "video_alert":
            interval_secs = 30
            if trigger_type == "interval_minutes":
                try:
                    interval_secs = int(trigger_val) * 60
                except ValueError:
                    interval_secs = 60
            elif trigger_type == "interval_seconds":
                try:
                    interval_secs = int(trigger_val)
                except ValueError:
                    interval_secs = 30
            
            last_run = rule.get("last_run_at")
            should_run = False
            if not last_run:
                should_run = True
            else:
                try:
                    last_dt = datetime.fromisoformat(last_run.replace("Z", "+00:00"))
                    diff = (datetime.now(timezone.utc) - last_dt).total_seconds()
                    if diff >= interval_secs:
                        should_run = True
                except Exception:
                    should_run = True

            if should_run:
                evaluate_video_automation(rule, now_local, is_manual=False)
            return

        # 5. Automações de Monitoramento de Mensagens do Slack (com verificação de presença e alertas)
        if auto_type == "slack_message_monitor" or trigger_type == "slack_new_message":
            interval_secs = 30
            if str(trigger_val).isdigit():
                try:
                    interval_secs = int(trigger_val)
                except ValueError:
                    interval_secs = 30
            
            last_run = rule.get("last_run_at")
            should_run = False
            if not last_run:
                should_run = True
            else:
                try:
                    last_dt = datetime.fromisoformat(last_run.replace("Z", "+00:00"))
                    diff = (datetime.now(timezone.utc) - last_dt).total_seconds()
                    if diff >= interval_secs:
                        should_run = True
                except Exception:
                    should_run = True

            if should_run:
                self.execute_slack_message_monitor(rule, now_local, is_manual=False)
            return

    def execute_calendar_reminder(self, rule: Dict[str, Any], now_local: datetime) -> Tuple[bool, str]:
        """Verifica a Google Agenda do usuário e avisa com antecedência no Telegram."""
        auto_id = rule["id"]
        user_email = rule["user_email"]
        payload = rule.get("action_payload", {}) or {}
        
        # Minutos de antecedência configurados (padrão: 15min)
        try:
            minutes_before = int(rule.get("trigger_value") or payload.get("minutes_before") or 15)
        except ValueError:
            minutes_before = 15

        # Configura credenciais do usuário
        gmail_email, gmail_pwd = db_get_google_credentials(user_email)

        if not gmail_email or not gmail_pwd:
            msg = "Credenciais Google não configuradas para este usuário."
            db_record_automation_run(auto_id, "warning", msg)
            return False, msg

        tg_cfg = db_get_telegram_config(user_email)
        bot_token = tg_cfg.get("bot_token")
        chat_id = tg_cfg.get("chat_id")

        if not bot_token or not chat_id or not tg_cfg.get("enabled"):
            msg = "Telegram não configurado ou desativado para receber notificações."
            db_record_automation_run(auto_id, "warning", msg)
            return False, msg

        set_calendar_credentials_context(gmail_email, gmail_pwd)
        cal, err = connect_caldav()
        if err or not cal:
            msg = f"Falha ao conectar no Google Calendar: {err}"
            db_record_automation_run(auto_id, "error", msg)
            return False, msg

        notified_count = 0
        try:
            # Janela de busca: de agora até (minutes_before + 5min de margem)
            start_window = now_local - timedelta(minutes=2)
            end_window = now_local + timedelta(minutes=minutes_before + 5)

            events = cal.search(start=start_window, end=end_window, expand=True)
            for e in (events or []):
                info = formatar_evento(e)
                raw_dt = info.get("raw_dtstart")
                event_uid = info.get("id") or info.get("titulo") or "evento"
                
                if raw_dt:
                    if isinstance(raw_dt, date) and not isinstance(raw_dt, datetime):
                        continue # Evento de dia inteiro ignorado para alerta de minutos
                    
                    # Converte para datetime local se necessário
                    if hasattr(raw_dt, "astimezone"):
                        ev_local = raw_dt.astimezone(now_local.tzinfo)
                    else:
                        ev_local = raw_dt

                    # Calcula minutos restantes até o início do compromisso
                    mins_left = int((ev_local - now_local).total_seconds() / 60)
                    
                    # Se estiver dentro da janela de alerta (ex: entre 0 e minutes_before + 2)
                    if 0 <= mins_left <= (minutes_before + 2):
                        event_key = f"cal_{event_uid}_{ev_local.strftime('%Y%m%d_%H%M')}"
                        if not db_is_event_already_notified(auto_id, event_key):
                            # Monta mensagem atraente no Telegram
                            titulo = info.get("titulo", "Compromisso")
                            inicio_str = info.get("inicio", ev_local.strftime("%H:%M"))
                            local = info.get("local", "")
                            desc = info.get("descricao", "")

                            msg_lines = [
                                "⏰ *Lembrete de Compromisso (Google Agenda)*",
                                "",
                                f"📌 *{titulo}*",
                                f"🕒 *Horário:* {inicio_str} (começa em aproximadamente *{mins_left} minutos*)",
                            ]
                            if local:
                                msg_lines.append(f"📍 *Local:* {local}")
                            if desc:
                                msg_lines.append(f"📝 *Notas:* {desc}")

                            msg_lines.append("\n_Tenha um excelente compromisso!_")
                            text_alert = "\n".join(msg_lines)

                            send_ok, _ = send_telegram_message(bot_token, chat_id, text_alert, parse_mode="Markdown")
                            
                            # Notificação no Slack se configurado
                            slack_cfg = db_get_slack_config(user_email)
                            if slack_cfg.get("enabled") and slack_cfg.get("notify_tasks") and (slack_cfg.get("bot_token") or slack_cfg.get("webhook_url")):
                                slack_blocks = build_slack_report_blocks(
                                    titulo=f"Lembrete de Compromisso: {titulo}",
                                    conteudo=f"*Início:* {inicio_str} (em ~{mins_left} min)\n" + (f"*Local:* {local}\n" if local else "") + (f"*Notas:* {desc}\n" if desc else ""),
                                    tipo_alerta="aviso"
                                )
                                send_slack_message_payload(
                                    slack_cfg.get("bot_token", ""),
                                    slack_cfg.get("webhook_url", ""),
                                    {"text": text_alert, "blocks": slack_blocks},
                                    channel=slack_cfg.get("default_channel", "")
                                )
                                system_logger.info(f"Lembrete de agenda enviado no Slack para {user_email}: '{titulo}'")
                                
                            if send_ok:
                                db_mark_event_notified(auto_id, user_email, event_key)
                                notified_count += 1
                                system_logger.info(f"Notificação de agenda enviada no Telegram para {user_email}: '{titulo}'")

            result_txt = f"Verificação concluída. {notified_count} alerta(s) enviado(s)."
            db_record_automation_run(auto_id, "success", result_txt)
            return True, result_txt

        except Exception as e_cal:
            err_msg = f"Erro ao verificar eventos da agenda: {e_cal}"
            db_record_automation_run(auto_id, "error", err_msg)
            return False, err_msg

    def execute_automation_action(self, rule: Dict[str, Any], is_manual: bool = False) -> Tuple[bool, str]:
        """Executa a ação correspondente da regra de automação."""
        auto_id = rule["id"]
        user_email = rule["user_email"]
        auto_type = rule.get("automation_type", "")
        action_type = rule.get("action_type", "")
        payload = rule.get("action_payload", {}) or {}

        tg_cfg = db_get_telegram_config(user_email)
        bot_token = tg_cfg.get("bot_token")
        chat_id = tg_cfg.get("chat_id")
        slack_cfg = db_get_slack_config(user_email)

        try:
            # 1. Resumo Diário / Matinal
            if auto_type == "daily_summary":
                return self._run_daily_summary(rule, bot_token, chat_id, slack_cfg, user_email)

            # 2. Automação de Luzes MQTT
            elif auto_type == "mqtt_schedule" or action_type == "mqtt_command":
                return self._run_mqtt_schedule(rule, bot_token, chat_id, slack_cfg, payload)

            # 3. Execução de Comando/Prompt Personalizado com IA
            elif auto_type == "custom_prompt" or action_type == "agent_prompt":
                return self._run_custom_prompt(rule, bot_token, chat_id, slack_cfg, user_email, payload)

            # 4. Lembrete de Agenda manual/forçado
            elif auto_type == "calendar_reminder":
                tz_local = dateutil.tz.tzlocal()
                return self.execute_calendar_reminder(rule, datetime.now(tz_local))

            # 5. Envio de mensagem no Telegram
            elif action_type == "telegram_alert":
                custom_msg = payload.get("message") or f"🔔 Notificação da Automação '{rule.get('name')}'"
                if bot_token and chat_id:
                    ok, resp = send_telegram_message(bot_token, chat_id, custom_msg, parse_mode="Markdown")
                    if ok:
                        db_record_automation_run(auto_id, "success", "Mensagem enviada no Telegram.")
                        return True, "Mensagem enviada com sucesso no Telegram."
                    else:
                        db_record_automation_run(auto_id, "error", f"Falha no Telegram: {resp}")
                        return False, resp
                return False, "Telegram não configurado para envio."

            # 6. Envio de mensagem ou relatório no Slack
            elif action_type == "slack_alert":
                custom_msg = payload.get("message") or f"🔔 Notificação da Automação '{rule.get('name')}'"
                if slack_cfg.get("bot_token") or slack_cfg.get("webhook_url"):
                    blocks = build_slack_report_blocks(
                        titulo=rule.get("name") or "Notificação de Automação",
                        conteudo=custom_msg,
                        tipo_alerta="info"
                    )
                    ok, resp = send_slack_message_payload(
                        slack_cfg.get("bot_token", ""),
                        slack_cfg.get("webhook_url", ""),
                        {"text": custom_msg, "blocks": blocks},
                        channel=slack_cfg.get("default_channel", "")
                    )
                    if ok:
                        db_record_automation_run(auto_id, "success", "Mensagem enviada no Slack.")
                        return True, "Mensagem enviada com sucesso no Slack."
                    else:
                        db_record_automation_run(auto_id, "error", f"Falha no Slack: {resp}")
                        return False, resp
                return False, "Slack não configurado para envio."

            # 7. Automação de Vídeo e Reconhecimento Facial
            elif auto_type.startswith("video_") or action_type == "video_alert":
                clear_video_cooldown(auto_id)
                tz_local = dateutil.tz.tzlocal()
                return evaluate_video_automation(rule, datetime.now(tz_local), is_manual=True)

            # 8. Automação de Monitoramento de Mensagens do Slack
            elif auto_type == "slack_message_monitor" or action_type == "multi_channel_alert":
                tz_local = dateutil.tz.tzlocal()
                return self.execute_slack_message_monitor(rule, datetime.now(tz_local), is_manual=is_manual)

            else:
                db_record_automation_run(auto_id, "success", "Regra executada.")
                return True, "Executado."

        except Exception as e_exec:
            err_msg = f"Erro ao executar automação {auto_id}: {e_exec}"
            system_logger.error(err_msg)
            db_record_automation_run(auto_id, "error", err_msg)
            return False, err_msg

    def _run_daily_summary(self, rule: Dict[str, Any], bot_token: str, chat_id: str, slack_cfg: Dict[str, Any], user_email: str) -> Tuple[bool, str]:
        """Gera e envia o resumo matinal/diário para o usuário no Telegram e Slack."""
        auto_id = rule["id"]
        today = date.today()
        dias = ["Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira", "Sexta-feira", "Sábado", "Domingo"]
        dia_nome = dias[today.weekday()]
        hoje_formatado = f"{dia_nome}, {today.day:02d}/{today.month:02d}/{today.year}"

        prof = get_user_profile(user_email)
        user_name = prof.get("name") or user_email.split("@")[0].capitalize()

        lines = [
            f"☀️ *Bom dia, {user_name}!*",
            f"Aqui está o seu *Resumo do Dia* preparado pela *Sexta-Feira* ({hoje_formatado}):\n",
        ]

        # 1. Compromissos da Agenda
        try:
            gmail_user, gmail_pwd = db_get_google_credentials(user_email)
            if gmail_user and gmail_pwd:
                set_calendar_credentials_context(gmail_user, gmail_pwd)
                tz_local = dateutil.tz.tzlocal()
                now_local = datetime.now(tz_local)
                end_of_day = now_local.replace(hour=23, minute=59, second=59)

                cal = connect_caldav(gmail_user, gmail_pwd)
                events = cal.date_search(start=now_local, end=end_of_day, expand=True)

                if events:
                    lines.append(f"🗓️ *Compromissos para hoje ({len(events)}):*")
                    for ev in events[:5]:
                        data_ev = formatar_evento(ev)
                        inicio_dt = data_ev.get("inicio_datetime")
                        hora_str = inicio_dt.astimezone(tz_local).strftime("%H:%M") if inicio_dt else "Horário a definir"
                        lines.append(f"  • *{hora_str}* — {data_ev.get('titulo', 'Sem título')}")
                    if len(events) > 5:
                        lines.append(f"  _... e mais {len(events)-5} eventos._")
                else:
                    lines.append("🗓️ *Agenda:* Nenhum compromisso agendado para hoje. Aproveite o dia!")
            else:
                lines.append("🗓️ *Agenda:* Integração com Google Agenda não configurada.")
        except Exception as e:
            system_logger.warning(f"Resumo diário - falha ao ler agenda: {e}")
            lines.append(f"🗓️ *Agenda:* Não foi possível consultar compromissos ({e}).")

        # 2. Tarefas Pendentes
        try:
            tasks = db_get_tasks(user_email, status="pending")
            if tasks:
                lines.append(f"\n📋 *Tarefas Pendentes ({len(tasks)}):*")
                for t in tasks[:4]:
                    prio = "⚡ " if t.get("priority") == "alta" else ""
                    due = f" (vence {t.get('due_time')})" if t.get("due_time") else ""
                    lines.append(f"  • {prio}{t.get('title')}{due}")
                if len(tasks) > 4:
                    lines.append(f"  _... e mais {len(tasks)-4} afazeres cadastrados._")
        except Exception as e:
            system_logger.warning(f"Resumo diário - falha ao ler tarefas: {e}")

        # 3. Status da Casa
        try:
            status_casa = relatorio_status_casa.invoke({})
            lines.append(f"\n💡 *Status da Casa:* {status_casa}")
        except Exception:
            pass

        lines.append("\n_Desejo a você um dia produtivo e cheio de realizações!_ 🚀")
        summary_text = "\n".join(lines)

        sent_any = False
        resp_msgs = []

        # Envio Telegram
        if bot_token and chat_id:
            ok_tg, resp_tg = send_telegram_message(bot_token, chat_id, summary_text, parse_mode="Markdown")
            if ok_tg:
                sent_any = True
                resp_msgs.append("Telegram")

        # Envio Slack
        if slack_cfg.get("enabled") and (slack_cfg.get("bot_token") or slack_cfg.get("webhook_url")):
            slack_blocks = build_slack_report_blocks(
                titulo="Resumo Diário da Residência & Tarefas",
                conteudo=summary_text,
                tipo_alerta="relatorio"
            )
            ok_slack, resp_slack = send_slack_message_payload(
                slack_cfg.get("bot_token", ""),
                slack_cfg.get("webhook_url", ""),
                {"text": summary_text, "blocks": slack_blocks},
                channel=slack_cfg.get("default_channel", "")
            )
            if ok_slack:
                sent_any = True
                resp_msgs.append("Slack")

        if sent_any:
            msg_success = f"Resumo diário enviado com sucesso ({', '.join(resp_msgs)})."
            db_record_automation_run(auto_id, "success", msg_success)
            return True, msg_success
        else:
            err = "Nenhum canal de notificação (Telegram/Slack) configurado ou disponível."
            db_record_automation_run(auto_id, "error", err)
            return False, err

    def _run_mqtt_schedule(self, rule: Dict[str, Any], bot_token: str, chat_id: str, slack_cfg: Dict[str, Any], payload: Dict[str, Any]) -> Tuple[bool, str]:
        """Aciona dispositivos e cômodos via MQTT conforme programado."""
        auto_id = rule["id"]
        room = payload.get("room", "todas")
        action = payload.get("action", "ON").upper()
        notify = payload.get("notify_telegram", True)

        res_mqtt = controlar_luzes.invoke({"room": room, "action": action})
        system_logger.info(f"Automação MQTT executada: {res_mqtt}")

        msg = f"💡 *Automação Residencial:* {res_mqtt}"
        if notify and bot_token and chat_id:
            send_telegram_message(bot_token, chat_id, msg, parse_mode="Markdown")
            
        if notify and slack_cfg.get("enabled") and (slack_cfg.get("bot_token") or slack_cfg.get("webhook_url")):
            send_slack_message_payload(
                slack_cfg.get("bot_token", ""),
                slack_cfg.get("webhook_url", ""),
                {"text": msg},
                channel=slack_cfg.get("default_channel", "")
            )

        db_record_automation_run(auto_id, "success", str(res_mqtt))
        return True, str(res_mqtt)

    def _run_custom_prompt(self, rule: Dict[str, Any], bot_token: str, chat_id: str, slack_cfg: Dict[str, Any], user_email: str, payload: Dict[str, Any]) -> Tuple[bool, str]:
        """Executa um comando inteligente do agente e notifica o usuário."""
        auto_id = rule["id"]
        prompt = payload.get("prompt", rule.get("name", ""))
        if not prompt:
            db_record_automation_run(auto_id, "error", "Prompt não informado.")
            return False, "Prompt não informado."

        try:
            try:
                from api.agent import processar_comando_agente
            except ImportError:
                from agent import processar_comando_agente

            prof = get_user_profile(user_email)
            ai_cfg = db_get_ai_config(user_email)
            api_key = (ai_cfg.get("api_key") or prof.get("api_key") or os.getenv("GEMINI_API_KEY") or "").strip()
            model_name = (ai_cfg.get("ai_model") or prof.get("ai_model") or os.getenv("DEFAULT_MODEL", "gemini-2.5-flash-lite")).strip()

            if not api_key:
                err_msg = "Chave de API não configurada no perfil para execução do comando."
                db_record_automation_run(auto_id, "error", err_msg)
                return False, err_msg

            broker_host = os.getenv("MQTT_BROKER", "test.mosquitto.org")
            broker_port = int(os.getenv("MQTT_PORT", "1883"))

            agent_name = (ai_cfg.get("agent_name") or "Sexta-Feira").strip()
            result = processar_comando_agente(
                pergunta=prompt,
                api_key=api_key,
                modelo=model_name,
                agent_name=agent_name,
                rooms=[],
                rooms_state={},
                broker_config={"broker": broker_host, "port": broker_port},
                user_email=user_email,
                user_profile=prof
            )

            reply = result.get("reply", "Comando executado.") if isinstance(result, dict) else str(result)
            actions = result.get("actions", []) if isinstance(result, dict) else []

            action_footer = ""
            if actions:
                action_strs = [f"• {str(a)}" for a in actions]
                action_footer = "\n\n⚡ *Ações executadas:*\n" + "\n".join(action_strs)

            final_msg = f"🤖 *Automação Agendada ('{rule.get('name')}')*\n\n{reply}{action_footer}"
            if bot_token and chat_id:
                send_telegram_message(bot_token, chat_id, final_msg)
                
            if slack_cfg.get("enabled") and (slack_cfg.get("bot_token") or slack_cfg.get("webhook_url")):
                blocks = build_slack_report_blocks(
                    titulo=f"Automação Agendada: {rule.get('name')}",
                    conteudo=f"{reply}{action_footer}",
                    tipo_alerta="info"
                )
                send_slack_message_payload(
                    slack_cfg.get("bot_token", ""),
                    slack_cfg.get("webhook_url", ""),
                    {"text": final_msg, "blocks": blocks},
                    channel=slack_cfg.get("default_channel", "")
                )

            db_record_automation_run(auto_id, "success", f"Executado: {reply[:100]}")
            return True, reply

        except Exception as e_agent:
            err = f"Falha ao executar comando do agente: {e_agent}"
            db_record_automation_run(auto_id, "error", err)
            return False, err

    def execute_slack_message_monitor(
        self,
        rule: Dict[str, Any],
        now_local: datetime,
        is_manual: bool = False
    ) -> Tuple[bool, str]:
        """
        Monitora novas mensagens em um canal do Slack.
        - Verifica se o usuário está presente na frente da câmera.
        - Se presente: fala com o usuário por voz ("Márcio, você recebeu uma mensagem...") e exibe Toast na tela.
        - Notifica no Telegram do usuário com o resumo da mensagem.
        """
        auto_id = rule["id"]
        user_email = rule["user_email"]
        payload = rule.get("action_payload", {}) or {}
        
        slack_cfg = db_get_slack_config(user_email)
        token = slack_cfg.get("bot_token", "").strip()
        if not token:
            msg = "Slack Bot Token não configurado para monitoramento de canal."
            if is_manual:
                db_record_automation_run(auto_id, "warning", msg)
            return False, msg
            
        tg_cfg = db_get_telegram_config(user_email)
        tg_token = tg_cfg.get("bot_token", "").strip()
        tg_chat_id = tg_cfg.get("chat_id", "").strip()
        tg_enabled = bool(tg_cfg.get("enabled", True))
        raw_channel = (payload.get("channel") or slack_cfg.get("default_channel") or rule.get("trigger_value") or "#importações").strip()
        if raw_channel.isdigit():
            raw_channel = (slack_cfg.get("default_channel") or "#importações").strip()
        target_channel = raw_channel or "#importações"
        channel_id, err_chan = _resolve_channel_id(token, target_channel)
        if not channel_id:
            msg = f"Falha ao resolver canal do Slack '{target_channel}': {err_chan}"
            db_record_automation_run(auto_id, "error", msg)
            return False, msg
            
        try:
            resp = requests.get(
                "https://slack.com/api/conversations.history",
                headers={"Authorization": f"Bearer {token}"},
                params={"channel": channel_id, "limit": 10},
                timeout=10
            )
            data = resp.json()
            if not data.get("ok"):
                err = data.get("error", "Erro ao obter histórico")
                msg = f"Falha ao consultar histórico do canal '{target_channel}': {err}"
                db_record_automation_run(auto_id, "error", msg)
                return False, msg
                
            raw_messages = data.get("messages", [])
            if not raw_messages:
                db_record_automation_run(auto_id, "success", f"Canal #{target_channel.lstrip('#')} monitorado (sem mensagens).")
                return True, "Nenhuma mensagem encontrada."
                
            # Na primeira execução real (não manual), marca mensagens existentes como lidas
            # para evitar notificar histórico antigo de uma vez só
            is_first_run = not rule.get("last_run_at")
            if is_first_run and not is_manual:
                for m in raw_messages:
                    ts = m.get("ts", "")
                    if ts:
                        db_mark_event_notified(auto_id, user_email, f"slack_msg_{channel_id}_{ts}")
                db_record_automation_run(auto_id, "success", f"Monitoramento iniciado para #{target_channel.lstrip('#')}.")
                return True, f"Monitoramento iniciado para #{target_channel.lstrip('#')}."
                
            new_messages = []
            for m in reversed(raw_messages):
                ts = m.get("ts", "")
                if not ts:
                    continue
                user_id = m.get("user")
                # Ignora mensagens do bot (para evitar loop de eco)
                if user_id == "U0C1JD5TRPS" or m.get("bot_id"):
                    continue
                    
                event_key = f"slack_msg_{channel_id}_{ts}"
                if not db_is_event_already_notified(auto_id, event_key) or is_manual:
                    new_messages.append((m, event_key))
                    if is_manual and len(new_messages) >= 1:
                        break # No teste manual, pega 1 para teste
                        
            if not new_messages:
                db_record_automation_run(auto_id, "success", f"Canal #{target_channel.lstrip('#')} verificado (sem novidades).")
                return True, "Sem novas mensagens."
                
            notify_tg = payload.get("notify_telegram", True)
            notify_screen = payload.get("notify_screen", True)
            check_presence = payload.get("check_camera_presence", True)
            speak_voice_option = payload.get("speak_voice", True)
            agent_action_prompt = payload.get("agent_action_prompt", "").strip()
            
            # 1. Verifica se o usuário está na frente de qualquer uma das câmeras cadastradas
            user_is_present = True
            presence_reason = "Verificação de presença desativada"
            detected_camera_name = ""
            if check_presence:
                try:
                    cams = db_get_user_cameras(user_email)
                    if not cams:
                        fallback_cfg = db_get_camera_config(user_email)
                        if fallback_cfg:
                            cams = [fallback_cfg]
                    
                    user_is_present = False
                    presence_reports = []
                    
                    for cam in cams:
                        if not cam.get("enabled", True):
                            continue
                        cam_name = cam.get("name") or f"Câmera {cam.get('id')}"
                        frame_bytes, err_cam = capture_camera_frame(config=cam, timeout=3.0, user_email=user_email)
                        if frame_bytes:
                            has_person, _, opencv_det = opencv_detect_person_or_face(
                                frame_bytes,
                                detection_mode="video_presence_detection",
                                min_confidence=0.45
                            )
                            if has_person:
                                user_is_present = True
                                detected_camera_name = cam_name
                                presence_reason = f"Pessoa detectada na câmera '{cam_name}' ({opencv_det})"
                                presence_reports.append(f"✅ {cam_name}: Pessoa detectada")
                                break
                            else:
                                presence_reports.append(f"⚪ {cam_name}: Nenhuma pessoa detectada")
                        else:
                            presence_reports.append(f"⚠️ {cam_name}: {err_cam or 'Inacessível'}")
                    
                    if not user_is_present:
                        presence_reason = " | ".join(presence_reports) if presence_reports else "Nenhuma câmera cadastrada ou acessível."
                except Exception as e_cam:
                    user_is_present = False
                    presence_reason = f"Erro na verificação de câmeras: {e_cam}"
                    
                system_logger.info(f"[SlackMonitor] Presença nas câmeras para {user_email}: {user_is_present} ({presence_reason})")
                
            notified_count = 0
            for m, event_key in new_messages:
                user_id = m.get("user")
                sender_name = _resolve_user_name(token, user_id) if user_id else (m.get("username") or "Sistema / Workflow")
                raw_text = m.get("text", "")
                clean_text = _format_slack_text(token, raw_text)
                
                ts_float = float(m.get("ts", 0))
                time_str = datetime.fromtimestamp(ts_float).strftime("%H:%M") if ts_float else now_local.strftime("%H:%M")
                
                # Monta a frase falada da assistente
                spoken_phrase = f"Atenção, você recebeu uma nova mensagem no Slack de {sender_name} no canal {target_channel.lstrip('#')}: {clean_text}"
                
                # Apenas fala se o usuário estiver presente na câmera e a opção de voz estiver ativa
                should_speak = bool(user_is_present and speak_voice_option)
                
                # 1. Envia no Telegram
                if notify_tg and tg_token and tg_chat_id and tg_enabled:
                    tg_text = (
                        f"💬 *Nova Mensagem no Slack* (`#{target_channel.lstrip('#')}`)\n\n"
                        f"👤 *De:* {sender_name}\n"
                        f"🕒 *Horário:* {time_str}\n"
                        f"📝 *Mensagem:*\n"
                        f"{clean_text}"
                    )
                    send_telegram_message(tg_token, tg_chat_id, tg_text, parse_mode="Markdown")
                    
                # 2. Adiciona alerta na tela do painel web (Toast + Fala por Voz se presente)
                if notify_screen:
                    db_add_screen_notification(
                        user_email=user_email,
                        title=f"Slack • #{target_channel.lstrip('#')}",
                        message=f"{sender_name}: {clean_text}",
                        source="slack",
                        icon="💬",
                        metadata={
                            "channel": target_channel,
                            "sender": sender_name,
                            "time": time_str,
                            "text": clean_text,
                            "user_present": user_is_present,
                            "presence_info": presence_reason,
                            "speak": should_speak,
                            "spoken_phrase": spoken_phrase
                        }
                    )
                    
                # 3. Disparo opcional de comando do agente
                if agent_action_prompt:
                    try:
                        from api.agent import processar_comando_agente
                    except ImportError:
                        from agent import processar_comando_agente
                    prompt_formatted = agent_action_prompt.replace("{mensagem}", clean_text).replace("{remetente}", sender_name)
                    processar_comando_agente(pergunta=prompt_formatted, user_email=user_email)
                    
                db_mark_event_notified(auto_id, user_email, event_key)
                notified_count += 1
                
            res_txt = f"{notified_count} mensagem(ns) do Slack processada(s) (Presença na câmera: {'Sim ✅' if user_is_present else 'Não ❌'})."
            db_record_automation_run(auto_id, "success", res_txt)
            return True, res_txt
            
        except Exception as e_proc:
            err_msg = f"Erro ao processar monitoramento do Slack: {e_proc}"
            db_record_automation_run(auto_id, "error", err_msg)
            return False, err_msg


# Instância global do motor
automation_engine = AutomationEngine(check_interval_seconds=30)

def run_automation_now(auto_id: int, user_email: str) -> Tuple[bool, str]:
    """Dispara a execução imediata de uma automação para teste pelo usuário."""
    rule = db_get_automation_by_id(user_email, auto_id)
    if not rule:
        return False, "Automação não encontrada."
    return automation_engine.execute_automation_action(rule, is_manual=True)

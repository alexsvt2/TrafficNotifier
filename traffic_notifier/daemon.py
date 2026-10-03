"""Proceso que queda corriendo: revisa cada `interval_minutes` y atiende los
comandos ("revisar", "detener", "iniciar") que el usuario manda al topic desde
la app ntfy."""

import json
import math
import queue
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

from . import ntfy
from . import static_map
from .check import FLUIDO, MODERADO, PESADO, MapSnapshots, in_window, run_check
from .config import Config, ConfigError, load_config
from .routes_api import get_traffic_path, get_travel_time

# Comandos más viejos se ignoran (llegan al reconectar tras suspender la Mac).
MAX_COMMAND_AGE = timedelta(minutes=5)
# Tope de espera del bucle: el reloj monotónico no avanza con la Mac dormida,
# así que se recalcula seguido con la hora real.
MAX_WAIT_S = 30
STATE_FILE = "state.json"
_ICONS = {level[3]: level[0] for level in (FLUIDO, MODERADO, PESADO)}


class Scheduler:
    """Decide cuándo revisar. Sin red propia: get_travel_time, send y
    snapshot (la imagen del mapa, opcional) se inyectan.

    paused_at: cuándo se mandó "detener". La pausa solo frena las revisiones
    automáticas y se acaba sola al día siguiente, a la hora de inicio.
    """

    def __init__(self, get_travel_time, send, snapshot=None, paused_at: datetime | None = None):
        self.get_travel_time = get_travel_time
        self.send = send
        self.snapshot = snapshot
        self.paused_at = paused_at
        self.last_check: datetime | None = None
        self.last_reminder: datetime | None = None
        # Última notificación de tráfico, para mostrarla fuera de ntfy (app de barra de menú).
        self.last_report: dict | None = None

    def paused(self, config: Config, now: datetime) -> bool:
        if self.paused_at and now >= _resume_time(self.paused_at, config):
            self.paused_at = None
        return self.paused_at is not None

    def tick(self, config: Config, now: datetime) -> bool:
        """Revisión automática si estamos en horario y ya pasó el intervalo.

        En pausa no revisa: recuerda cada `reminder_minutes` que sigue conectado.
        """
        if not in_window(now, config):
            return False
        if self.paused(config, now):
            every = timedelta(minutes=config.reminder_minutes)
            if not self.last_reminder or now - self.last_reminder >= every:
                self.last_reminder = now
                self._notify(config, "double_vertical_bar",
                             f"Sigo conectado, pero las revisiones automáticas están detenidas "
                             f"{_until(self.paused_at, config, now)}. "
                             f"Manda «{config.start_keyword}» para reanudarlas.")
            return False
        if self.last_check and now - self.last_check < timedelta(minutes=config.interval_minutes):
            return False
        self._check(config, now)
        return True

    def on_message(self, config: Config, message: ntfy.Message, now: datetime) -> bool:
        """Atiende un mensaje del topic. Devuelve True si hizo una revisión."""
        # Nuestros propios avisos también llegan al topic; nunca son un comando.
        text = message.text.strip().casefold()
        if text not in {k.casefold() for k in (config.keyword, config.stop_keyword, config.start_keyword)}:
            return False
        if now - message.time > MAX_COMMAND_AGE:
            return False
        if text == config.stop_keyword.casefold():
            self.paused_at = self.last_reminder = now
            self._notify(config, "double_vertical_bar",
                         f"Revisiones automáticas detenidas {_until(now, config, now)}. "
                         f"Manda «{config.start_keyword}» para reanudarlas antes; "
                         f"«{config.keyword}» sigue funcionando.")
            return False
        if text == config.start_keyword.casefold():
            if self.paused(config, now):
                self.paused_at = None
                self._notify(config, "arrow_forward", "Revisiones automáticas reanudadas.")
            else:
                self._notify(config, "arrow_forward", "Las revisiones automáticas ya estaban activas.")
            return False
        if self.last_check:
            wait = self.last_check + timedelta(minutes=config.cooldown_minutes) - now
            if wait > timedelta(0):
                self._notify(config, "hourglass",
                             f"Acabo de revisar. Espera {_duration(wait)} para volver a pedirlo.")
                return False
        # Revisa aunque esté en pausa o fuera de horario, y recorre la siguiente automática.
        self._check(config, now)
        return True

    def seconds_until_due(self, config: Config, now: datetime) -> float:
        if self.paused(config, now):
            return MAX_WAIT_S
        if not self.last_check:
            return 0
        due = self.last_check + timedelta(minutes=config.interval_minutes)
        return max(0.0, (due - now).total_seconds())

    def _check(self, config: Config, now: datetime) -> None:
        # Se marca antes de enviar: si ntfy falla, Google ya se consultó y no
        # hay que reintentar cada vuelta del bucle.
        self.last_check = now

        def send(**kwargs):
            self.last_report = {
                "at": now.isoformat(timespec="seconds"),
                "title": kwargs["title"],
                "message": kwargs["message"],
                "icon": _ICONS.get(kwargs["tags"][0], "⚠️"),
            }
            self.send(**kwargs)

        run_check(config, now, self.get_travel_time, send, force=True, snapshot=self.snapshot)

    def _notify(self, config: Config, tag: str, message: str) -> None:
        self.send(
            topic=config.ntfy_topic,
            title="TrafficNotifier",
            message=message,
            priority=2,
            tags=(tag,),
            server=config.ntfy_server,
        )


def serve(config_path: Path, log) -> None:
    """Bucle infinito; launchd lo mantiene vivo (KeepAlive)."""
    config = load_config(config_path)
    # El estado se guarda en disco: launchd puede relanzar el proceso en cualquier
    # momento, y la app de barra de menú lo lee de ahí.
    state_path = config_path.with_name(STATE_FILE)
    paused_at, report = load_state(state_path)
    scheduler = Scheduler(get_travel_time, ntfy.send, MapSnapshots(get_traffic_path, static_map.render),
                          paused_at=paused_at)
    scheduler.last_report = report
    saved = (paused_at, report)
    inbox: queue.Queue = queue.Queue()
    threading.Thread(
        target=_listen_forever, args=(config.ntfy_topic, config.ntfy_server, inbox, log), daemon=True
    ).start()
    log(f"Escuchando '{config.keyword}', '{config.stop_keyword}' e '{config.start_keyword}' en ntfy; "
        f"revisión cada {config.interval_minutes} min{' (en pausa)' if paused_at else ''}.")

    while True:
        try:
            config = load_config(config_path)  # los cambios aplican solos
        except ConfigError as e:
            log(f"ERROR: {e} (sigo con la configuración anterior)")

        if _guard(log, lambda: scheduler.tick(config, datetime.now())):
            log("Revisión automática enviada.")
        # Aquí ya se atendió el último comando y tick ya venció la pausa si tocaba.
        current = (scheduler.paused_at, scheduler.last_report)
        if current != saved:
            if current[0] != saved[0]:
                log("Revisiones automáticas detenidas." if current[0] else "Revisiones automáticas reanudadas.")
            saved = current
            save_state(state_path, *saved)

        wait = min(MAX_WAIT_S, max(1.0, scheduler.seconds_until_due(config, datetime.now())))
        try:
            message = inbox.get(timeout=wait)
        except queue.Empty:
            continue
        if _guard(log, lambda: scheduler.on_message(config, message, datetime.now())):
            log("Revisión a demanda enviada.")


def load_state(path: Path) -> tuple:
    """(paused_at, last_report) guardados; (None, None) sin archivo o ilegible."""
    try:
        data = json.loads(path.read_text())
        paused_at = datetime.fromisoformat(data["paused_at"]) if data.get("paused_at") else None
        report = data.get("last_report")
        return paused_at, report if isinstance(report, dict) else None
    except (OSError, ValueError, TypeError, AttributeError):
        return None, None


def save_state(path: Path, paused_at: datetime | None, report: dict | None) -> None:
    data = {"paused_at": paused_at.isoformat() if paused_at else None, "last_report": report}
    try:
        # Escritura atómica: la app puede estar leyendo el archivo.
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False))
        tmp.replace(path)
    except OSError:
        pass  # el estado sigue en memoria; solo se perdería al reiniciar


def _listen_forever(topic: str, server: str, inbox: queue.Queue, log) -> None:
    since = str(int(time.time()))  # al reconectar, no perder lo que llegó mientras
    backoff = 5
    while True:
        connected_at = time.monotonic()
        try:
            for message in ntfy.listen(topic, server, since=since):
                since = message.id
                inbox.put(message)
        except ntfy.NotifyError as e:
            log(f"ERROR: {e}")
        if time.monotonic() - connected_at > 60:
            backoff = 5
        time.sleep(backoff)
        backoff = min(backoff * 2, 60)


def _guard(log, action) -> bool:
    """Un fallo de ntfy se loguea sin tumbar el proceso."""
    try:
        return action()
    except ntfy.NotifyError as e:
        log(f"ERROR: {e}")
        return False


def _resume_time(paused_at: datetime, config: Config) -> datetime:
    """La pausa termina al día siguiente de pedirla, a la hora de inicio."""
    return datetime.combine(paused_at.date() + timedelta(days=1), config.start)


def _until(paused_at: datetime, config: Config, now: datetime) -> str:
    resume = _resume_time(paused_at, config)
    day = "hoy" if resume.date() == now.date() else "mañana"
    return f"hasta {day} a las {resume:%H:%M}"


def _duration(delta: timedelta) -> str:
    seconds = math.ceil(delta.total_seconds())
    return f"{seconds} s" if seconds < 120 else f"{math.ceil(seconds / 60)} min"

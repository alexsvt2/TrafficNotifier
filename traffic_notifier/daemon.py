"""Proceso que queda corriendo: revisa cada `interval_minutes` y atiende el
comando (p. ej. "revisar") que el usuario manda al topic desde la app ntfy."""

import math
import queue
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

from . import ntfy
from .check import in_window, run_check
from .config import Config, ConfigError, load_config
from .routes_api import get_travel_time

# Comandos más viejos se ignoran (llegan al reconectar tras suspender la Mac).
MAX_COMMAND_AGE = timedelta(minutes=5)
# Tope de espera del bucle: el reloj monotónico no avanza con la Mac dormida,
# así que se recalcula seguido con la hora real.
MAX_WAIT_S = 30


class Scheduler:
    """Decide cuándo revisar. Sin red propia: get_travel_time y send se inyectan."""

    def __init__(self, get_travel_time, send):
        self.get_travel_time = get_travel_time
        self.send = send
        self.last_check: datetime | None = None

    def tick(self, config: Config, now: datetime) -> bool:
        """Revisión automática si estamos en horario y ya pasó el intervalo."""
        if not in_window(now, config):
            return False
        if self.last_check and now - self.last_check < timedelta(minutes=config.interval_minutes):
            return False
        self._check(config, now)
        return True

    def on_message(self, config: Config, message: ntfy.Message, now: datetime) -> bool:
        """Atiende un mensaje del topic. Devuelve True si hizo una revisión."""
        # Nuestros propios avisos también llegan al topic; nunca son el comando.
        if message.text.strip().casefold() != config.keyword.casefold():
            return False
        if now - message.time > MAX_COMMAND_AGE:
            return False
        if self.last_check:
            wait = self.last_check + timedelta(minutes=config.cooldown_minutes) - now
            if wait > timedelta(0):
                self.send(
                    topic=config.ntfy_topic,
                    title="TrafficNotifier",
                    message=f"Acabo de revisar. Espera {_duration(wait)} para volver a pedirlo.",
                    priority=2,
                    tags=("hourglass",),
                    server=config.ntfy_server,
                )
                return False
        # Revisa aunque esté fuera de horario, y recorre la siguiente automática.
        self._check(config, now)
        return True

    def seconds_until_due(self, config: Config, now: datetime) -> float:
        if not self.last_check:
            return 0
        due = self.last_check + timedelta(minutes=config.interval_minutes)
        return max(0.0, (due - now).total_seconds())

    def _check(self, config: Config, now: datetime) -> None:
        # Se marca antes de enviar: si ntfy falla, Google ya se consultó y no
        # hay que reintentar cada vuelta del bucle.
        self.last_check = now
        run_check(config, now, self.get_travel_time, self.send, force=True)


def serve(config_path: Path, log) -> None:
    """Bucle infinito; launchd lo mantiene vivo (KeepAlive)."""
    config = load_config(config_path)
    scheduler = Scheduler(get_travel_time, ntfy.send)
    inbox: queue.Queue = queue.Queue()
    threading.Thread(
        target=_listen_forever, args=(config.ntfy_topic, config.ntfy_server, inbox, log), daemon=True
    ).start()
    log(f"Escuchando '{config.keyword}' en ntfy; revisión cada {config.interval_minutes} min.")

    while True:
        try:
            config = load_config(config_path)  # los cambios aplican solos
        except ConfigError as e:
            log(f"ERROR: {e} (sigo con la configuración anterior)")

        if _guard(log, lambda: scheduler.tick(config, datetime.now())):
            log("Revisión automática enviada.")

        wait = min(MAX_WAIT_S, max(1.0, scheduler.seconds_until_due(config, datetime.now())))
        try:
            message = inbox.get(timeout=wait)
        except queue.Empty:
            continue
        if _guard(log, lambda: scheduler.on_message(config, message, datetime.now())):
            log("Revisión a demanda enviada.")


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


def _duration(delta: timedelta) -> str:
    seconds = math.ceil(delta.total_seconds())
    return f"{seconds} s" if seconds < 120 else f"{math.ceil(seconds / 60)} min"

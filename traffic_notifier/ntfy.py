"""Envío de notificaciones push con ntfy (https://ntfy.sh)."""

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from typing import Iterator


class NotifyError(Exception):
    """No se pudo enviar la notificación o escuchar el topic."""


@dataclass(frozen=True)
class Message:
    id: str
    time: datetime  # hora local en que ntfy recibió el mensaje
    text: str


def send(
    topic: str,
    title: str,
    message: str,
    priority: int = 3,
    tags: tuple = (),
    server: str = "https://ntfy.sh",
    timeout: float = 15,
) -> None:
    # Título y tags van como query params: los headers HTTP no admiten
    # acentos ni emojis de forma fiable.
    params = {"title": title, "priority": str(priority)}
    if tags:
        params["tags"] = ",".join(tags)
    url = f"{server.rstrip('/')}/{urllib.parse.quote(topic)}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, data=message.encode("utf-8"), method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout):
            pass
    except urllib.error.URLError as e:
        raise NotifyError(f"ntfy falló: {e}") from e


def listen(topic: str, server: str = "https://ntfy.sh", since: str | None = None,
           timeout: float = 90) -> Iterator[Message]:
    """Mensajes publicados en el topic, en vivo, hasta que se cae la conexión.

    since: id de mensaje o timestamp unix; sin él solo llegan mensajes nuevos.
    ntfy manda un keepalive cada ~45 s, así que `timeout` detecta conexiones
    muertas (p. ej. después de suspender la Mac).
    """
    url = f"{server.rstrip('/')}/{urllib.parse.quote(topic)}/json"
    if since:
        url += "?" + urllib.parse.urlencode({"since": since})
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            for line in response:
                message = parse_event(line)
                if message:
                    yield message
    except (urllib.error.URLError, OSError) as e:
        raise NotifyError(f"Se perdió la conexión con ntfy: {e}") from e


def parse_event(line: bytes) -> Message | None:
    """Una línea del stream JSON de ntfy; None si no es un mensaje."""
    try:
        event = json.loads(line)
    except ValueError:
        return None
    if not isinstance(event, dict) or event.get("event") != "message":
        return None
    return Message(
        id=str(event.get("id", "")),
        time=datetime.fromtimestamp(event.get("time", 0)),
        text=str(event.get("message", "")),
    )

"""Envío de notificaciones push con ntfy (https://ntfy.sh)."""

import urllib.error
import urllib.parse
import urllib.request


class NotifyError(Exception):
    """No se pudo enviar la notificación."""


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

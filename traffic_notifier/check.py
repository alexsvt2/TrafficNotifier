"""Revisión de todas las rutas y armado de la notificación."""

from datetime import datetime

from .config import Config
from .routes_api import TrafficError, TravelTime

# (emoji, nombre, prioridad ntfy, tag ntfy)
FLUIDO = ("🟢", "fluido", 2, "green_circle")
MODERADO = ("🟡", "moderado", 3, "yellow_circle")
PESADO = ("🔴", "pesado", 4, "red_circle")


def in_window(now: datetime, config: Config) -> bool:
    return config.start <= now.time() <= config.end


def classify(travel: TravelTime, config: Config) -> tuple:
    ratio = travel.duration_s / travel.typical_s if travel.typical_s else 1
    if ratio > config.heavy:
        return PESADO
    if ratio >= config.moderate:
        return MODERADO
    return FLUIDO


def run_check(config: Config, now: datetime, get_travel_time, send, force: bool = False) -> bool:
    """Revisa todas las rutas y manda una sola notificación.

    Devuelve False si no se revisó por estar fuera del horario.
    """
    if not force and not in_window(now, config):
        return False

    lines, levels = [], []
    for route in config.routes:
        try:
            travel = get_travel_time(route.origin, route.destination, config.google_api_key)
        except TrafficError as e:
            lines.append(f"{route.name} ⚠️ {e}")
            continue
        level = classify(travel, config)
        levels.append(level)
        lines.append(_format_line(route.name, travel, level))

    if levels:
        worst = max(levels, key=lambda lvl: lvl[2])
        priority, tags = worst[2], (worst[3],)
    else:
        priority, tags = 2, ("warning",)  # todas las rutas fallaron

    send(
        topic=config.ntfy_topic,
        title=f"Tráfico {now:%H:%M}",
        message="\n".join(lines),
        priority=priority,
        tags=tags,
        server=config.ntfy_server,
    )
    return True


def _format_line(name: str, travel: TravelTime, level: tuple) -> str:
    minutes = round(travel.duration_s / 60)
    typical = round(travel.typical_s / 60)
    delay = minutes - typical
    km = travel.distance_m / 1000
    return f"{name} {level[0]} {minutes} min (normal {typical}, {delay:+d}) · {km:.0f} km"

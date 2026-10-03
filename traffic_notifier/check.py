"""Revisión de todas las rutas y armado de la notificación."""

import urllib.parse
from datetime import datetime, timedelta

from .config import Config, Route
from .routes_api import TrafficError, TravelTime
from .static_map import MapError

# (emoji, nombre, prioridad ntfy, tag ntfy)
FLUIDO = ("🟢", "fluido", 2, "green_circle")
MODERADO = ("🟡", "moderado", 3, "yellow_circle")
PESADO = ("🔴", "pesado", 4, "red_circle")

SEPARATOR = "– – – – – – – – – –"


def in_window(now: datetime, config: Config) -> bool:
    return config.start <= now.time() <= config.end


def classify(travel: TravelTime, config: Config) -> tuple:
    ratio = travel.duration_s / travel.typical_s if travel.typical_s else 1
    if ratio > config.heavy:
        return PESADO
    if ratio >= config.moderate:
        return MODERADO
    return FLUIDO


class MapSnapshots:
    """Imagen de las rutas en 🔴, como máximo una por ruta cada
    `config.map_every_minutes` (el trazo con tráfico se cobra como Enterprise)."""

    def __init__(self, get_traffic_path, render):
        self.get_traffic_path = get_traffic_path
        self.render = render
        self.last: dict[Route, datetime] = {}

    def __call__(self, config: Config, routes: list, now: datetime) -> bytes | None:
        if not config.map_enabled:
            return None
        every = timedelta(minutes=config.map_every_minutes)
        due = [r for r in routes if r not in self.last or now - self.last[r] >= every]
        if not due:
            return None
        for route in due:
            # Se marca antes de consultar: si algo falla, no se reintenta cada 20 min.
            self.last[route] = now
        paths = [self.get_traffic_path(r.origin, r.destination, config.google_api_key) for r in due]
        return self.render(paths, config.google_api_key)


def run_check(config: Config, now: datetime, get_travel_time, send, force: bool = False,
              snapshot=None) -> bool:
    """Revisa todas las rutas y manda una sola notificación.

    snapshot(config, rutas_en_rojo, now) -> PNG | None, opcional: imagen adjunta.
    Devuelve False si no se revisó por estar fuera del horario.
    """
    if not force and not in_window(now, config):
        return False

    blocks, levels, heavy = [], [], []
    for route in config.routes:
        try:
            travel = get_travel_time(route.origin, route.destination, config.google_api_key)
        except TrafficError as e:
            blocks.append(f"⚠️ {route.name}\n{e}")
            continue
        level = classify(travel, config)
        levels.append(level)
        blocks.append(_format_line(route.name, travel, level))
        if level is PESADO:
            heavy.append(route)

    if levels:
        worst = max(levels, key=lambda lvl: lvl[2])
        priority, tags = worst[2], (worst[3],)
    else:
        priority, tags = 2, ("warning",)  # todas las rutas fallaron

    groups = _groups(config.routes)
    message = f"\n{SEPARATOR}\n".join("\n".join(blocks[i] for i in group) for group in groups)

    image = None
    if snapshot and heavy:
        try:
            image = snapshot(config, heavy, now)
        except (TrafficError, MapError) as e:
            message += f"\n⚠️ Mapa: {e}"

    send(
        topic=config.ntfy_topic,
        title=f"Tráfico {now:%H:%M}",
        message=message,
        priority=priority,
        tags=tags,
        server=config.ntfy_server,
        attachment=image,
        # Un botón por grupo (ntfy admite 3): con la ida basta para ver el camino.
        actions=tuple(_maps_button(config.routes[group[0]]) for group in groups[:3]),
    )
    return True


def _groups(routes) -> list:
    """Índices de las rutas agrupadas: cada ruta con su regreso, si la
    siguiente es la misma al revés."""
    groups, i = [], 0
    while i < len(routes):
        a = routes[i]
        b = routes[i + 1] if i + 1 < len(routes) else None
        size = 2 if b and (b.origin, b.destination) == (a.destination, a.origin) else 1
        groups.append(range(i, i + size))
        i += size
    return groups


def _maps_button(route: Route) -> tuple:
    query = urllib.parse.urlencode(
        {"api": "1", "origin": route.origin, "destination": route.destination, "travelmode": "driving"}
    )
    return f"🗺️ {route.name}", f"https://www.google.com/maps/dir/?{query}"


def _format_line(name: str, travel: TravelTime, level: tuple) -> str:
    minutes = round(travel.duration_s / 60)
    typical = round(travel.typical_s / 60)
    delay = minutes - typical
    km = travel.distance_m / 1000
    vs_normal = f"+{delay} min de lo normal" if delay > 0 else "como siempre"
    return f"{level[0]} {name}\n{minutes} min · {vs_normal} · {km:.0f} km"

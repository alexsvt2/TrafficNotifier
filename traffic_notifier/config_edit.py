"""Cambios a config.toml desde la terminal o la app, sin tocar la API key.

`edit` es la única puerta: aplica el cambio en memoria, valida el resultado
con `load_config`, comprueba que la API key quedó idéntica, guarda un respaldo
y reemplaza el archivo de forma atómica. Si algo falla, config.toml no cambia.
"""

import json
import os
import re
import shutil
import tomllib
from pathlib import Path

from .config import ConfigError, load_config

HEADER = (
    "# Configuración de TrafficNotifier. No se sube a git: contiene la API key.\n"
    "# Se puede editar a mano o con `python -m traffic_notifier place|route|set`;\n"
    "# esos comandos reescriben el archivo y no conservan los comentarios.\n"
)
SECRET = "google_api_key"
# Lo que `set` puede cambiar. La API key no está: solo se edita a mano.
SETTINGS = {
    "ntfy_topic", "ntfy_server",
    "schedule.start", "schedule.end", "schedule.interval_minutes",
    "command.keyword", "command.cooldown_minutes", "command.stop", "command.start", "command.reminder_minutes",
    "thresholds.moderate", "thresholds.heavy",
    "map.enabled", "map.every_minutes",
}
_BARE_KEY = re.compile(r"^[A-Za-z0-9_-]+$")
_MAPS_PIN = re.compile(r"!3d(-?\d+(?:\.\d+)?)!4d(-?\d+(?:\.\d+)?)")
_MAPS_CENTER = re.compile(r"@(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)")


def read_raw(path: Path) -> dict:
    """config.toml tal cual está escrito (los lugares sin resolver)."""
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except FileNotFoundError:
        raise ConfigError(f"No existe {path}. Copia config.example.toml a config.toml y llénalo.")
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{path} no es TOML válido: {e}")


def public(raw: dict) -> dict:
    """La configuración sin la API key, para mostrarla o pasarla a la app."""
    return {key: value for key, value in raw.items() if key != SECRET}


def edit(path: Path, change) -> None:
    """Aplica change(raw) a config.toml; lanza ConfigError y no guarda si queda inválido."""
    raw = read_raw(path)
    secret = raw.get(SECRET)
    change(raw)
    text = dumps(raw)
    tmp = path.with_name(path.name + ".tmp")
    try:
        # 0600: el archivo lleva la API key.
        with os.fdopen(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w", encoding="utf-8") as f:
            f.write(text)
        load_config(tmp)
        if tomllib.loads(text).get(SECRET) != secret:
            raise ConfigError("El cambio alteraría la API key; no se guardó nada.")
        backup = path.with_name(path.name + ".bak")
        shutil.copy2(path, backup)
        os.chmod(backup, 0o600)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def add_place(raw: dict, label: str, where: str) -> None:
    label = label.strip()
    if not label:
        raise ConfigError("El lugar necesita una etiqueta.")
    raw.setdefault("places", {})[label] = parse_location(where)


def remove_place(raw: dict, label: str) -> None:
    places = raw.get("places", {})
    if label not in places:
        raise ConfigError(f"No hay un lugar llamado '{label}'.")
    used = [i for i, r in enumerate(raw.get("routes", []), 1) if label in (r.get("origin"), r.get("destination"))]
    if used:
        raise ConfigError(f"'{label}' se usa en la(s) ruta(s) #{', #'.join(map(str, used))}; quítalas primero.")
    del places[label]
    if not places:
        del raw["places"]


def add_route(raw: dict, origin: str, destination: str, name: str | None = None, round_trip: bool = False) -> None:
    places = raw.get("places", {})
    ends = [end if end in places else parse_location(end) for end in (origin, destination)]
    if ends[0] == ends[1]:
        raise ConfigError("El origen y el destino son el mismo.")
    routes = raw.setdefault("routes", [])
    route = {"origin": ends[0], "destination": ends[1]}
    if name:
        route = {"name": name, **route}
    routes.append(route)
    if round_trip:
        # El regreso va justo después para que la notificación los agrupe.
        routes.append({"origin": ends[1], "destination": ends[0]})


def remove_route(raw: dict, number: int) -> None:
    routes = raw.get("routes", [])
    if not 1 <= number <= len(routes):
        raise ConfigError(f"No hay ruta #{number}; hay {len(routes)}.")
    del routes[number - 1]


def set_value(raw: dict, setting: str, value: str) -> None:
    if setting not in SETTINGS:
        hint = " La API key solo se cambia editando config.toml a mano." if setting == SECRET else ""
        raise ConfigError(f"'{setting}' no se puede cambiar con set.{hint} Opciones: {', '.join(sorted(SETTINGS))}.")
    *section, key = setting.split(".")
    table = raw.setdefault(section[0], {}) if section else raw
    table[key] = _parse_value(value)


def parse_location(text: str) -> str:
    """Dirección o "lat,lng"; de un link de Google Maps saca las coordenadas del pin."""
    text = text.strip()
    if not text:
        raise ConfigError("Falta la dirección o las coordenadas.")
    if not text.startswith(("http://", "https://")):
        return text
    match = _MAPS_PIN.search(text) or _MAPS_CENTER.search(text)
    if not match:
        raise ConfigError("No encontré coordenadas en ese link; pásalas como lat,lng.")
    return f"{match[1]},{match[2]}"


def _parse_value(text: str):
    text = text.strip()
    if text.lower() in ("true", "false"):
        return text.lower() == "true"
    for number in (int, float):
        try:
            return number(text)
        except ValueError:
            pass
    return text


def dumps(raw: dict) -> str:
    """TOML para la forma de config.toml: valores sueltos, tablas y listas de tablas."""
    scalars = {k: v for k, v in raw.items() if not isinstance(v, (dict, list))}
    blocks = [HEADER + "".join(_line(k, v) for k, v in scalars.items())]
    for name, value in raw.items():
        if isinstance(value, dict):
            blocks.append(f"[{_key(name)}]\n" + "".join(_line(k, v) for k, v in value.items()))
    for name, value in raw.items():
        if isinstance(value, list):
            blocks.extend(f"[[{_key(name)}]]\n" + "".join(_line(k, v) for k, v in item.items()) for item in value)
    return "\n".join(blocks)


def _line(key: str, value) -> str:
    if isinstance(value, bool):
        text = "true" if value else "false"
    elif isinstance(value, (int, float)):
        text = repr(value)
    elif isinstance(value, str):
        text = json.dumps(value, ensure_ascii=False)  # las cadenas JSON son cadenas TOML válidas
    else:
        raise ConfigError(f"No sé escribir '{key}' en config.toml.")
    return f"{_key(key)} = {text}\n"


def _key(key: str) -> str:
    return key if _BARE_KEY.match(key) else json.dumps(key, ensure_ascii=False)

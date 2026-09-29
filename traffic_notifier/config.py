"""Carga y validación de config.toml."""

import tomllib
from dataclasses import dataclass
from datetime import time
from pathlib import Path


class ConfigError(Exception):
    """config.toml falta o es inválido."""


@dataclass(frozen=True)
class Route:
    name: str
    origin: str
    destination: str


@dataclass(frozen=True)
class Config:
    google_api_key: str
    ntfy_topic: str
    routes: tuple
    start: time = time(7, 0)
    end: time = time(22, 0)
    interval_minutes: int = 30
    keyword: str = "revisar"
    cooldown_minutes: float = 2
    moderate: float = 1.15
    heavy: float = 1.40
    ntfy_server: str = "https://ntfy.sh"


def load_config(path: Path) -> Config:
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except FileNotFoundError:
        raise ConfigError(f"No existe {path}. Copia config.example.toml a config.toml y llénalo.")
    except tomllib.TOMLDecodeError as e:
        raise ConfigError(f"{path} no es TOML válido: {e}")

    schedule = data.get("schedule", {})
    thresholds = data.get("thresholds", {})
    command = data.get("command", {})
    config = Config(
        google_api_key=_required_str(data, "google_api_key"),
        ntfy_topic=_required_str(data, "ntfy_topic"),
        ntfy_server=data.get("ntfy_server", Config.ntfy_server),
        routes=tuple(_route(r, i) for i, r in enumerate(data.get("routes", []), 1)),
        start=_time(schedule.get("start", "07:00"), "schedule.start"),
        end=_time(schedule.get("end", "22:00"), "schedule.end"),
        interval_minutes=_number(schedule, "interval_minutes", Config.interval_minutes, "schedule", minimum=1),
        keyword=str(command.get("keyword", Config.keyword)).strip(),
        cooldown_minutes=_number(command, "cooldown_minutes", Config.cooldown_minutes, "command", minimum=0),
        moderate=float(thresholds.get("moderate", Config.moderate)),
        heavy=float(thresholds.get("heavy", Config.heavy)),
    )
    if not config.routes:
        raise ConfigError("Agrega al menos una ruta con [[routes]].")
    if not config.keyword:
        raise ConfigError("command.keyword no puede estar vacío.")
    if not 1 <= config.moderate <= config.heavy:
        raise ConfigError("Los umbrales deben cumplir 1 <= moderate <= heavy.")
    return config


def _required_str(data: dict, key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip() or value.strip() == "...":
        raise ConfigError(f"Falta '{key}' en config.toml.")
    return value.strip()


def _route(data: dict, index: int) -> Route:
    try:
        return Route(name=data.get("name") or f"Ruta {index}", origin=data["origin"], destination=data["destination"])
    except KeyError as e:
        raise ConfigError(f"La ruta #{index} no tiene {e.args[0]}.")


def _time(value: str, key: str) -> time:
    try:
        return time.fromisoformat(value)
    except ValueError:
        raise ConfigError(f"{key} debe tener formato HH:MM, no '{value}'.")


def _number(table: dict, key: str, default: float, section: str, minimum: float) -> float:
    value = table.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value < minimum:
        raise ConfigError(f"{section}.{key} debe ser un número >= {minimum}, no '{value}'.")
    return value

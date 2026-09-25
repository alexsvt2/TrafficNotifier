"""Cliente mínimo de Google Routes API (computeRoutes) con tráfico."""

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass

ENDPOINT = "https://routes.googleapis.com/directions/v2:computeRoutes"
FIELD_MASK = "routes.duration,routes.staticDuration,routes.distanceMeters"
_LATLNG = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")


class TrafficError(Exception):
    """La consulta de tráfico falló (red, API key, ruta inexistente...)."""


@dataclass(frozen=True)
class TravelTime:
    duration_s: int  # con el tráfico actual
    typical_s: int  # sin tráfico
    distance_m: int


def get_travel_time(origin: str, destination: str, api_key: str, timeout: float = 20) -> TravelTime:
    """Tiempo de viaje en coche de origin a destination.

    origin/destination aceptan una dirección en texto o "lat,lng".
    """
    body = {
        "origin": _waypoint(origin),
        "destination": _waypoint(destination),
        "travelMode": "DRIVE",
        "routingPreference": "TRAFFIC_AWARE",
    }
    request = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(body).encode(),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": FIELD_MASK,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        raise TrafficError(f"Routes API respondió {e.code}: {_error_message(detail)}") from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise TrafficError(f"No se pudo contactar Routes API: {e}") from e
    return parse_response(payload)


def parse_response(payload: dict) -> TravelTime:
    routes = payload.get("routes") or []
    if not routes:
        raise TrafficError("Google no encontró una ruta entre esos puntos")
    route = routes[0]
    duration = _seconds(route.get("duration"))
    return TravelTime(
        duration_s=duration,
        typical_s=_seconds(route.get("staticDuration")) or duration,
        distance_m=int(route.get("distanceMeters", 0)),
    )


def _waypoint(place: str) -> dict:
    match = _LATLNG.match(place)
    if match:
        lat, lng = (float(g) for g in match.groups())
        return {"location": {"latLng": {"latitude": lat, "longitude": lng}}}
    return {"address": place}


def _seconds(value) -> int:
    # La API devuelve duraciones como "1234s".
    if not value:
        return 0
    return int(float(str(value).rstrip("s")))


def _error_message(detail: str) -> str:
    try:
        return json.loads(detail)["error"]["message"]
    except (ValueError, KeyError, TypeError):
        return detail[:300]

"""Cliente mínimo de Google Routes API (computeRoutes) con tráfico."""

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass

ENDPOINT = "https://routes.googleapis.com/directions/v2:computeRoutes"
FIELD_MASK = "routes.duration,routes.staticDuration,routes.distanceMeters"
# Pedir el tráfico por tramo cobra la consulta como Enterprise (más cara que
# Pro), por eso va aparte y solo se pide cuando hace falta el mapa.
PATH_FIELD_MASK = "routes.polyline.encodedPolyline,routes.travelAdvisory.speedReadingIntervals"
_LATLNG = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")


class TrafficError(Exception):
    """La consulta de tráfico falló (red, API key, ruta inexistente...)."""


@dataclass(frozen=True)
class TravelTime:
    duration_s: int  # con el tráfico actual
    typical_s: int  # sin tráfico
    distance_m: int


@dataclass(frozen=True)
class TrafficPath:
    polyline: str  # formato "encoded polyline" de Google
    # (índice inicial, índice final, "NORMAL" | "SLOW" | "TRAFFIC_JAM") sobre los puntos del polyline
    intervals: tuple


def get_travel_time(origin: str, destination: str, api_key: str, timeout: float = 20) -> TravelTime:
    """Tiempo de viaje en coche de origin a destination.

    origin/destination aceptan una dirección en texto o "lat,lng".
    """
    return parse_response(_compute_routes(origin, destination, api_key, FIELD_MASK, timeout))


def get_traffic_path(origin: str, destination: str, api_key: str, timeout: float = 20) -> TrafficPath:
    """Trazo de la ruta con la velocidad de cada tramo. Se cobra como Enterprise."""
    payload = _compute_routes(origin, destination, api_key, PATH_FIELD_MASK, timeout,
                              extraComputations=["TRAFFIC_ON_POLYLINE"])
    return parse_path(payload)


def _compute_routes(origin: str, destination: str, api_key: str, field_mask: str, timeout: float,
                    **extra) -> dict:
    body = {
        "origin": _waypoint(origin),
        "destination": _waypoint(destination),
        "travelMode": "DRIVE",
        "routingPreference": "TRAFFIC_AWARE",
        **extra,
    }
    request = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(body).encode(),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": field_mask,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        raise TrafficError(f"Routes API respondió {e.code}: {_error_message(detail)}") from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise TrafficError(f"No se pudo contactar Routes API: {e}") from e


def parse_response(payload: dict) -> TravelTime:
    route = _first_route(payload)
    duration = _seconds(route.get("duration"))
    return TravelTime(
        duration_s=duration,
        typical_s=_seconds(route.get("staticDuration")) or duration,
        distance_m=int(route.get("distanceMeters", 0)),
    )


def parse_path(payload: dict) -> TrafficPath:
    route = _first_route(payload)
    polyline = (route.get("polyline") or {}).get("encodedPolyline")
    if not polyline:
        raise TrafficError("Google no devolvió el trazo de la ruta")
    # La API omite los campos en cero: un tramo sin startPolylinePointIndex empieza en 0.
    intervals = tuple(
        (int(i.get("startPolylinePointIndex", 0)), int(i.get("endPolylinePointIndex", 0)), i.get("speed", "NORMAL"))
        for i in (route.get("travelAdvisory") or {}).get("speedReadingIntervals", [])
    )
    return TrafficPath(polyline, intervals)


def _first_route(payload: dict) -> dict:
    routes = payload.get("routes") or []
    if not routes:
        raise TrafficError("Google no encontró una ruta entre esos puntos")
    return routes[0]


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

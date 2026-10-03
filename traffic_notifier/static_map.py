"""Imagen PNG de las rutas con los atascos pintados (Google Maps Static API).

La URL lleva la API key, así que la imagen se descarga aquí y se sube como
archivo: la URL nunca debe llegar al topic de ntfy, que es público.
"""

import urllib.error
import urllib.parse
import urllib.request

from .routes_api import TrafficPath

ENDPOINT = "https://maps.googleapis.com/maps/api/staticmap"
ROUTE_STYLE = "color:0x1A73E8CC|weight:5"
SPEED_STYLES = {
    "SLOW": "color:0xF29900FF|weight:7",
    "TRAFFIC_JAM": "color:0xD93025FF|weight:8",
}


class MapError(Exception):
    """No se pudo generar la imagen del mapa."""


def render(paths: list, api_key: str, timeout: float = 20) -> bytes:
    """PNG con cada ruta en azul y sus tramos lentos/atascados encima."""
    try:
        with urllib.request.urlopen(map_url(paths, api_key), timeout=timeout) as response:
            if not response.headers.get("Content-Type", "").startswith("image/"):
                raise MapError("Static Maps no devolvió una imagen")
            return response.read()
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace").strip()
        raise MapError(f"Static Maps respondió {e.code}: {detail[:200]}") from e
    except (urllib.error.URLError, TimeoutError) as e:
        raise MapError(f"No se pudo contactar Static Maps: {e}") from e


def map_url(paths: list, api_key: str) -> str:
    params = [("size", "640x480"), ("scale", "2"), ("format", "png")]
    for path in paths:
        params.append(("path", f"{ROUTE_STYLE}|enc:{path.polyline}"))
    # Los tramos van después para quedar encima de la ruta.
    for path in paths:
        params.extend(("path", f"{style}|enc:{encoded}") for style, encoded in _slow_segments(path))
    for path in paths:
        points = decode(path.polyline)
        params.append(("markers", f"size:mid|color:green|label:A|{_latlng(points[0])}"))
        params.append(("markers", f"size:mid|color:red|label:B|{_latlng(points[-1])}"))
    params.append(("key", api_key))
    return f"{ENDPOINT}?{urllib.parse.urlencode(params)}"


def _slow_segments(path: TrafficPath):
    points = decode(path.polyline)
    for start, end, speed in path.intervals:
        style = SPEED_STYLES.get(speed)
        if style and end > start:
            yield style, encode(points[start:end + 1])


def _latlng(point: tuple) -> str:
    return f"{point[0]:.5f},{point[1]:.5f}"


# Algoritmo "encoded polyline" de Google:
# https://developers.google.com/maps/documentation/utilities/polylinealgorithm

def decode(polyline: str) -> list:
    points, index, lat, lng = [], 0, 0, 0
    while index < len(polyline):
        for axis in (0, 1):
            shift = result = 0
            while True:
                byte = ord(polyline[index]) - 63
                index += 1
                result |= (byte & 0x1F) << shift
                shift += 5
                if byte < 0x20:
                    break
            delta = ~(result >> 1) if result & 1 else result >> 1
            if axis == 0:
                lat += delta
            else:
                lng += delta
        points.append((lat / 1e5, lng / 1e5))
    return points


def encode(points: list) -> str:
    out, prev_lat, prev_lng = [], 0, 0
    for lat, lng in points:
        lat_e5, lng_e5 = round(lat * 1e5), round(lng * 1e5)
        for delta in (lat_e5 - prev_lat, lng_e5 - prev_lng):
            value = ~(delta << 1) if delta < 0 else delta << 1
            while value >= 0x20:
                out.append(chr((0x20 | (value & 0x1F)) + 63))
                value >>= 5
            out.append(chr(value + 63))
        prev_lat, prev_lng = lat_e5, lng_e5
    return "".join(out)

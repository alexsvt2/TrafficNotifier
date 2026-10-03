import unittest
import urllib.parse

from traffic_notifier.routes_api import TrafficPath
from traffic_notifier.static_map import decode, encode, map_url

# Ejemplo de la documentación de Google.
POINTS = [(38.5, -120.2), (40.7, -120.95), (43.252, -126.453)]
ENCODED = "_p~iF~ps|U_ulLnnqC_mqNvxq`@"


class PolylineTest(unittest.TestCase):
    def test_encode(self):
        self.assertEqual(encode(POINTS), ENCODED)

    def test_decode(self):
        self.assertEqual(decode(ENCODED), POINTS)


class MapUrlTest(unittest.TestCase):
    def test_paints_only_slow_segments(self):
        path = TrafficPath(ENCODED, ((0, 1, "NORMAL"), (1, 2, "TRAFFIC_JAM")))
        params = urllib.parse.parse_qs(urllib.parse.urlparse(map_url([path], "secret")).query)
        route, jam = params["path"]
        self.assertTrue(route.endswith(f"enc:{ENCODED}"))
        self.assertIn("0xD93025", jam)
        self.assertTrue(jam.endswith("enc:" + encode(POINTS[1:3])))
        self.assertEqual(params["key"], ["secret"])
        self.assertEqual(len(params["markers"]), 2)


if __name__ == "__main__":
    unittest.main()

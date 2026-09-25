import unittest

from traffic_notifier.routes_api import TrafficError, TravelTime, _waypoint, parse_response


class ParseResponseTest(unittest.TestCase):
    def test_parses_durations(self):
        payload = {"routes": [{"duration": "2520s", "staticDuration": "1800s", "distanceMeters": 18000}]}
        self.assertEqual(parse_response(payload), TravelTime(2520, 1800, 18000))

    def test_missing_static_duration_falls_back_to_duration(self):
        payload = {"routes": [{"duration": "600s", "distanceMeters": 100}]}
        self.assertEqual(parse_response(payload).typical_s, 600)

    def test_no_routes_raises(self):
        with self.assertRaises(TrafficError):
            parse_response({})


class WaypointTest(unittest.TestCase):
    def test_lat_lng(self):
        self.assertEqual(
            _waypoint("19.4326, -99.1332"),
            {"location": {"latLng": {"latitude": 19.4326, "longitude": -99.1332}}},
        )

    def test_address(self):
        self.assertEqual(_waypoint("Reforma 222, CDMX"), {"address": "Reforma 222, CDMX"})


if __name__ == "__main__":
    unittest.main()

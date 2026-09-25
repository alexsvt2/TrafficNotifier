import unittest
from datetime import datetime

from traffic_notifier.check import run_check
from traffic_notifier.config import Config, Route
from traffic_notifier.routes_api import TrafficError, TravelTime

CONFIG = Config(
    google_api_key="key",
    ntfy_topic="topic",
    routes=(Route("A → B", "a", "b"), Route("B → C", "b", "c")),
)
MORNING = datetime(2026, 9, 25, 8, 30)
NIGHT = datetime(2026, 9, 25, 23, 0)


class FakeSend:
    def __init__(self):
        self.calls = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)


def fixed(travel_by_origin):
    def get_travel_time(origin, destination, api_key):
        result = travel_by_origin[origin]
        if isinstance(result, Exception):
            raise result
        return result
    return get_travel_time


class RunCheckTest(unittest.TestCase):
    def test_outside_window_does_nothing(self):
        send = FakeSend()
        ran = run_check(CONFIG, NIGHT, fixed({}), send)
        self.assertFalse(ran)
        self.assertEqual(send.calls, [])

    def test_force_ignores_window(self):
        send = FakeSend()
        travel = TravelTime(600, 600, 5000)
        self.assertTrue(run_check(CONFIG, NIGHT, fixed({"a": travel, "b": travel}), send, force=True))
        self.assertEqual(len(send.calls), 1)

    def test_window_edges_are_inclusive(self):
        travel = TravelTime(600, 600, 5000)
        for now in (datetime(2026, 9, 25, 7, 0), datetime(2026, 9, 25, 22, 0)):
            self.assertTrue(run_check(CONFIG, now, fixed({"a": travel, "b": travel}), FakeSend()))

    def test_one_notification_with_worst_level(self):
        send = FakeSend()
        travels = {"a": TravelTime(600, 600, 5000), "b": TravelTime(2520, 1680, 18000)}
        run_check(CONFIG, MORNING, fixed(travels), send)
        [call] = send.calls
        self.assertEqual(call["priority"], 4)
        self.assertEqual(call["tags"], ("red_circle",))
        self.assertEqual(call["title"], "Tráfico 08:30")
        self.assertIn("A → B 🟢 10 min (normal 10, +0) · 5 km", call["message"])
        self.assertIn("B → C 🔴 42 min (normal 28, +14) · 18 km", call["message"])

    def test_moderate_threshold(self):
        send = FakeSend()
        travel = TravelTime(1150, 1000, 1000)  # exactamente 1.15
        run_check(CONFIG, MORNING, fixed({"a": travel, "b": travel}), send)
        self.assertEqual(send.calls[0]["priority"], 3)

    def test_failed_route_does_not_block_others(self):
        send = FakeSend()
        travels = {"a": TrafficError("sin ruta"), "b": TravelTime(600, 600, 5000)}
        run_check(CONFIG, MORNING, fixed(travels), send)
        message = send.calls[0]["message"]
        self.assertIn("A → B ⚠️ sin ruta", message)
        self.assertIn("B → C 🟢", message)
        self.assertEqual(send.calls[0]["priority"], 2)

    def test_all_routes_failing_still_notifies(self):
        send = FakeSend()
        err = TrafficError("API key inválida")
        run_check(CONFIG, MORNING, fixed({"a": err, "b": err}), send)
        self.assertEqual(send.calls[0]["tags"], ("warning",))


if __name__ == "__main__":
    unittest.main()

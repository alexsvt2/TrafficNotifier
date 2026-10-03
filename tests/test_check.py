import unittest
from dataclasses import replace
from datetime import datetime, timedelta

from traffic_notifier.check import MapSnapshots, run_check
from traffic_notifier.config import Config, Route
from traffic_notifier.routes_api import TrafficError, TrafficPath, TravelTime
from traffic_notifier.static_map import MapError

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


FREE = TravelTime(600, 600, 5000)
JAM = TravelTime(2520, 1680, 18000)  # 1.5 → 🔴


class FakeSnapshot:
    def __init__(self, result=b"png"):
        self.result = result
        self.calls = []

    def __call__(self, config, routes, now):
        self.calls.append([r.name for r in routes])
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


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
        self.assertIn("🟢 A → B\n10 min · como siempre · 5 km", call["message"])
        self.assertIn("🔴 B → C\n42 min · +14 min de lo normal · 18 km", call["message"])

    def test_round_trips_are_grouped(self):
        config = Config(
            google_api_key="key",
            ntfy_topic="topic",
            routes=(Route("A → B", "a", "b"), Route("B → A", "b", "a"), Route("C → D", "c", "d")),
        )
        send = FakeSend()
        travel = TravelTime(600, 600, 5000)
        run_check(config, MORNING, fixed({"a": travel, "b": travel, "c": travel}), send)
        groups = send.calls[0]["message"].split("\n– – – – – – – – – –\n")
        self.assertEqual(len(groups), 2)
        self.assertTrue(groups[0].startswith("🟢 A → B\n"))
        self.assertIn("\n🟢 B → A\n", groups[0])
        self.assertTrue(groups[1].startswith("🟢 C → D\n"))

    def test_maps_buttons_one_per_group(self):
        send = FakeSend()
        run_check(CONFIG, MORNING, fixed({"a": FREE, "b": FREE}), send)
        labels = [label for label, url in send.calls[0]["actions"]]
        self.assertEqual(labels, ["🗺️ A → B", "🗺️ B → C"])
        self.assertIn("origin=a&destination=b", send.calls[0]["actions"][0][1])

    def test_image_only_for_heavy_routes(self):
        snapshot, send = FakeSnapshot(), FakeSend()
        run_check(CONFIG, MORNING, fixed({"a": FREE, "b": JAM}), send, snapshot=snapshot)
        self.assertEqual(snapshot.calls, [["B → C"]])
        self.assertEqual(send.calls[0]["attachment"], b"png")

    def test_no_heavy_routes_no_image(self):
        snapshot, send = FakeSnapshot(), FakeSend()
        run_check(CONFIG, MORNING, fixed({"a": FREE, "b": FREE}), send, snapshot=snapshot)
        self.assertEqual(snapshot.calls, [])
        self.assertIsNone(send.calls[0]["attachment"])

    def test_map_failure_still_notifies(self):
        snapshot, send = FakeSnapshot(MapError("403")), FakeSend()
        run_check(CONFIG, MORNING, fixed({"a": JAM, "b": JAM}), send, snapshot=snapshot)
        self.assertIsNone(send.calls[0]["attachment"])
        self.assertIn("⚠️ Mapa: 403", send.calls[0]["message"])

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
        self.assertIn("⚠️ A → B\nsin ruta", message)
        self.assertIn("🟢 B → C", message)
        self.assertEqual(send.calls[0]["priority"], 2)

    def test_all_routes_failing_still_notifies(self):
        send = FakeSend()
        err = TrafficError("API key inválida")
        run_check(CONFIG, MORNING, fixed({"a": err, "b": err}), send)
        self.assertEqual(send.calls[0]["tags"], ("warning",))


class MapSnapshotsTest(unittest.TestCase):
    def setUp(self):
        self.paths = []
        self.renders = []

        def get_traffic_path(origin, destination, api_key):
            self.paths.append(origin)
            return TrafficPath("enc", ())

        def render(paths, api_key):
            self.renders.append(len(paths))
            return b"png"

        self.snapshots = MapSnapshots(get_traffic_path, render)
        self.a, self.b = CONFIG.routes

    def test_at_most_once_per_route_per_interval(self):
        self.assertEqual(self.snapshots(CONFIG, [self.a], MORNING), b"png")
        self.assertIsNone(self.snapshots(CONFIG, [self.a], MORNING + timedelta(minutes=59)))
        # Solo la ruta que no ha salido en imagen.
        self.snapshots(CONFIG, [self.a, self.b], MORNING + timedelta(minutes=59))
        self.assertEqual(self.paths, ["a", "b"])
        self.snapshots(CONFIG, [self.a], MORNING + timedelta(minutes=60))
        self.assertEqual(self.paths, ["a", "b", "a"])

    def test_failed_lookup_still_counts(self):
        def failing(origin, destination, api_key):
            raise TrafficError("x")

        snapshots = MapSnapshots(failing, lambda paths, key: b"png")
        with self.assertRaises(TrafficError):
            snapshots(CONFIG, [self.a], MORNING)
        self.assertIsNone(snapshots(CONFIG, [self.a], MORNING + timedelta(minutes=20)))

    def test_disabled(self):
        config = replace(CONFIG, map_enabled=False)
        self.assertIsNone(self.snapshots(config, [self.a], MORNING))
        self.assertEqual(self.paths, [])


if __name__ == "__main__":
    unittest.main()

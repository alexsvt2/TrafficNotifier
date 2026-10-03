import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

from traffic_notifier.config import Config, Route
from traffic_notifier.daemon import Scheduler, load_paused_at, save_paused_at
from traffic_notifier.ntfy import Message
from traffic_notifier.routes_api import TravelTime

CONFIG = Config(
    google_api_key="key",
    ntfy_topic="topic",
    routes=(Route("A → B", "a", "b"),),
    interval_minutes=20,
    cooldown_minutes=2,
)
MORNING = datetime(2026, 9, 29, 8, 0)
NIGHT = datetime(2026, 9, 29, 23, 0)


class Fakes:
    def __init__(self):
        self.lookups = 0
        self.sent = []

    def get_travel_time(self, origin, destination, api_key):
        self.lookups += 1
        return TravelTime(600, 600, 5000)

    def send(self, **kwargs):
        self.sent.append(kwargs)


def scheduler():
    fakes = Fakes()
    return Scheduler(fakes.get_travel_time, fakes.send), fakes


def command(at: datetime, text: str = "revisar") -> Message:
    return Message(id="x", time=at, text=text)


class TickTest(unittest.TestCase):
    def test_outside_window_does_nothing(self):
        s, fakes = scheduler()
        self.assertFalse(s.tick(CONFIG, NIGHT))
        self.assertEqual(fakes.lookups, 0)

    def test_first_tick_in_window_checks(self):
        s, fakes = scheduler()
        self.assertTrue(s.tick(CONFIG, MORNING))
        self.assertEqual(len(fakes.sent), 1)

    def test_waits_for_interval(self):
        s, fakes = scheduler()
        s.tick(CONFIG, MORNING)
        self.assertFalse(s.tick(CONFIG, MORNING + timedelta(minutes=19)))
        self.assertTrue(s.tick(CONFIG, MORNING + timedelta(minutes=20)))
        self.assertEqual(fakes.lookups, 2)


class CommandTest(unittest.TestCase):
    def test_checks_even_outside_window(self):
        s, fakes = scheduler()
        self.assertTrue(s.on_message(CONFIG, command(NIGHT), NIGHT))
        self.assertEqual(fakes.lookups, 1)

    def test_cooldown_replies_without_calling_google(self):
        s, fakes = scheduler()
        s.tick(CONFIG, MORNING)
        now = MORNING + timedelta(seconds=30)
        self.assertFalse(s.on_message(CONFIG, command(now), now))
        self.assertEqual(fakes.lookups, 1)
        self.assertIn("Espera 90 s", fakes.sent[-1]["message"])

    def test_after_cooldown_checks(self):
        s, fakes = scheduler()
        s.tick(CONFIG, MORNING)
        now = MORNING + timedelta(minutes=2)
        self.assertTrue(s.on_message(CONFIG, command(now), now))
        self.assertEqual(fakes.lookups, 2)

    def test_command_postpones_next_automatic_check(self):
        s, fakes = scheduler()
        s.tick(CONFIG, MORNING)
        manual = MORNING + timedelta(minutes=10)
        s.on_message(CONFIG, command(manual), manual)
        self.assertFalse(s.tick(CONFIG, MORNING + timedelta(minutes=20)))
        self.assertTrue(s.tick(CONFIG, manual + timedelta(minutes=20)))

    def test_ignores_other_text_and_own_notifications(self):
        s, fakes = scheduler()
        for text in ("hola", "A → B 🟢 10 min (normal 10, +0) · 5 km", "revisar ya"):
            self.assertFalse(s.on_message(CONFIG, command(MORNING, text), MORNING))
        self.assertEqual(fakes.sent, [])

    def test_keyword_ignores_case_and_spaces(self):
        s, _ = scheduler()
        self.assertTrue(s.on_message(CONFIG, command(MORNING, "  Revisar\n"), MORNING))

    def test_custom_keyword(self):
        s, _ = scheduler()
        config = replace(CONFIG, keyword="?")
        self.assertTrue(s.on_message(config, command(MORNING, "?"), MORNING))

    def test_ignores_stale_command(self):
        s, fakes = scheduler()
        self.assertFalse(s.on_message(CONFIG, command(MORNING - timedelta(minutes=6)), MORNING))
        self.assertEqual(fakes.lookups, 0)


class PauseTest(unittest.TestCase):
    def paused(self, at=MORNING):
        s, fakes = scheduler()
        s.on_message(CONFIG, command(at, "detener"), at)
        return s, fakes

    def test_stop_confirms_and_skips_automatic_checks(self):
        s, fakes = self.paused()
        self.assertIn("hasta mañana a las 07:00", fakes.sent[-1]["message"])
        self.assertFalse(s.tick(CONFIG, MORNING + timedelta(minutes=20)))
        self.assertEqual(fakes.lookups, 0)

    def test_reminds_while_paused(self):
        s, fakes = self.paused()
        s.tick(CONFIG, MORNING + timedelta(minutes=59))
        self.assertEqual(len(fakes.sent), 1)  # solo la confirmación
        s.tick(CONFIG, MORNING + timedelta(minutes=60))
        s.tick(CONFIG, MORNING + timedelta(minutes=61))
        self.assertEqual(len(fakes.sent), 2)
        self.assertIn("Sigo conectado", fakes.sent[-1]["message"])
        self.assertIn("«iniciar»", fakes.sent[-1]["message"])

    def test_no_reminders_outside_window(self):
        s, fakes = self.paused()
        s.tick(CONFIG, NIGHT)
        self.assertEqual(len(fakes.sent), 1)

    def test_resumes_next_day_at_start(self):
        s, fakes = self.paused()
        tomorrow = MORNING + timedelta(days=1)
        self.assertTrue(s.paused(CONFIG, tomorrow.replace(hour=6, minute=59)))
        self.assertTrue(s.tick(CONFIG, tomorrow.replace(hour=7, minute=0)))
        self.assertIsNone(s.paused_at)
        self.assertEqual(fakes.lookups, 1)

    def test_start_resumes(self):
        s, fakes = self.paused()
        now = MORNING + timedelta(minutes=5)
        self.assertFalse(s.on_message(CONFIG, command(now, "Iniciar"), now))
        self.assertIn("reanudadas", fakes.sent[-1]["message"])
        self.assertTrue(s.tick(CONFIG, now))

    def test_start_when_not_paused(self):
        s, fakes = scheduler()
        s.on_message(CONFIG, command(MORNING, "iniciar"), MORNING)
        self.assertIn("ya estaban activas", fakes.sent[-1]["message"])

    def test_manual_check_works_while_paused(self):
        s, fakes = self.paused()
        self.assertTrue(s.on_message(CONFIG, command(MORNING), MORNING))
        self.assertIsNotNone(s.paused_at)

    def test_ignores_stale_stop(self):
        s, fakes = scheduler()
        s.on_message(CONFIG, command(MORNING - timedelta(minutes=6), "detener"), MORNING)
        self.assertIsNone(s.paused_at)

    def test_restored_pause_expires(self):
        fakes = Fakes()
        s = Scheduler(fakes.get_travel_time, fakes.send, paused_at=MORNING - timedelta(days=3))
        self.assertTrue(s.tick(CONFIG, MORNING))

    def test_state_file_round_trip(self):
        path = Path(tempfile.mkdtemp()) / "state.json"
        self.assertIsNone(load_paused_at(path))
        save_paused_at(path, MORNING)
        self.assertEqual(load_paused_at(path), MORNING)
        save_paused_at(path, None)
        self.assertIsNone(load_paused_at(path))
        path.write_text("basura")
        self.assertIsNone(load_paused_at(path))


if __name__ == "__main__":
    unittest.main()

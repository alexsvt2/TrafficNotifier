import tempfile
import tomllib
import unittest
from pathlib import Path

from traffic_notifier import config_edit
from traffic_notifier.config import ConfigError, load_config

BASE = (
    "# comentario\n"
    'google_api_key = "secreta"\nntfy_topic = "t"\n'
    '[schedule]\ninterval_minutes = 20\n'
    '[[routes]]\nname = "A → B"\norigin = "1.0,2.0"\ndestination = "Calle 5, Centro"\n'
)


def config_file(text: str = BASE) -> Path:
    path = Path(tempfile.mkdtemp()) / "config.toml"
    path.write_text(text)
    return path


class EditTest(unittest.TestCase):
    def test_places_and_round_trip(self):
        path = config_file()
        config_edit.edit(path, lambda raw: config_edit.add_place(raw, "Casa", "17.5,-92.5"))
        config_edit.edit(path, lambda raw: config_edit.add_place(raw, "Casa Roger", "17.9,-92.9"))
        config_edit.edit(path, lambda raw: config_edit.add_route(raw, "Casa", "Casa Roger", round_trip=True))
        routes = load_config(path).routes
        self.assertEqual([r.name for r in routes], ["A → B", "Casa → Casa Roger", "Casa Roger → Casa"])
        self.assertEqual((routes[1].origin, routes[1].destination), ("17.5,-92.5", "17.9,-92.9"))
        self.assertEqual(routes[0].destination, "Calle 5, Centro")

    def test_moving_a_place_moves_its_routes(self):
        path = config_file()
        config_edit.edit(path, lambda raw: config_edit.add_place(raw, "Casa", "1,1"))
        config_edit.edit(path, lambda raw: config_edit.add_route(raw, "Casa", "9,9"))
        config_edit.edit(path, lambda raw: config_edit.add_place(raw, "Casa", "2,2"))
        self.assertEqual(load_config(path).routes[1].origin, "2,2")

    def test_keeps_api_key_and_makes_backup(self):
        path = config_file()
        config_edit.edit(path, lambda raw: config_edit.set_value(raw, "schedule.interval_minutes", "25"))
        self.assertEqual(load_config(path).google_api_key, "secreta")
        self.assertEqual(load_config(path).interval_minutes, 25)
        self.assertEqual(path.with_name("config.toml.bak").read_text(), BASE)

    def test_refuses_to_change_api_key(self):
        path = config_file()
        with self.assertRaisesRegex(ConfigError, "a mano"):
            config_edit.edit(path, lambda raw: config_edit.set_value(raw, "google_api_key", "otra"))
        with self.assertRaisesRegex(ConfigError, "API key"):
            config_edit.edit(path, lambda raw: raw.update(google_api_key="otra"))
        self.assertEqual(path.read_text(), BASE)

    def test_invalid_change_leaves_file_untouched(self):
        path = config_file()
        with self.assertRaisesRegex(ConfigError, "interval_minutes"):
            config_edit.edit(path, lambda raw: config_edit.set_value(raw, "schedule.interval_minutes", "0"))
        with self.assertRaisesRegex(ConfigError, "ruta"):
            config_edit.edit(path, lambda raw: config_edit.remove_route(raw, 1))
        self.assertEqual(path.read_text(), BASE)
        self.assertEqual([p.name for p in path.parent.iterdir()], ["config.toml"])

    def test_place_in_use_cannot_be_removed(self):
        path = config_file()
        config_edit.edit(path, lambda raw: config_edit.add_place(raw, "Casa", "1,1"))
        config_edit.edit(path, lambda raw: config_edit.add_route(raw, "Casa", "9,9"))
        with self.assertRaisesRegex(ConfigError, "#2"):
            config_edit.edit(path, lambda raw: config_edit.remove_place(raw, "Casa"))
        config_edit.edit(path, lambda raw: config_edit.remove_route(raw, 2))
        config_edit.edit(path, lambda raw: config_edit.remove_place(raw, "Casa"))
        self.assertNotIn("places", config_edit.read_raw(path))

    def test_public_hides_api_key(self):
        self.assertNotIn("google_api_key", config_edit.public(config_edit.read_raw(config_file())))


class ParseLocationTest(unittest.TestCase):
    def test_maps_link_uses_the_pin_not_the_map_center(self):
        link = "https://www.google.com/maps/place/X/@17.9815,-92.9066,18z/data=!4m4!3m3!8m2!3d17.980228!4d-92.907358?entry=ttu"
        self.assertEqual(config_edit.parse_location(link), "17.980228,-92.907358")

    def test_maps_link_without_pin_uses_center(self):
        self.assertEqual(config_edit.parse_location("https://www.google.com/maps/@17.5,-92.5,15z"), "17.5,-92.5")

    def test_link_without_coordinates(self):
        with self.assertRaises(ConfigError):
            config_edit.parse_location("https://maps.app.goo.gl/abc123")

    def test_plain_text_passes_through(self):
        self.assertEqual(config_edit.parse_location(" 17.5,-92.5 "), "17.5,-92.5")


class DumpsTest(unittest.TestCase):
    def test_round_trips_through_toml(self):
        raw = {
            "google_api_key": 'con "comillas" y \\',
            "schedule": {"start": "07:00", "interval_minutes": 20},
            "thresholds": {"moderate": 1.15},
            "map": {"enabled": False},
            "places": {"Casa Roger": "17.9,-92.9", "UT": "Av. Universidad 1, Villahermosa"},
            "routes": [{"name": "Casa → UT", "origin": "Casa Roger", "destination": "UT"}],
        }
        self.assertEqual(tomllib.loads(config_edit.dumps(raw)), raw)


if __name__ == "__main__":
    unittest.main()

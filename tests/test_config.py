import tempfile
import unittest
from datetime import time
from pathlib import Path

from traffic_notifier.config import ConfigError, load_config

EXAMPLE = Path(__file__).resolve().parent.parent / "config.example.toml"


def write(text: str) -> Path:
    f = tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False)
    f.write(text)
    f.close()
    return Path(f.name)


class LoadConfigTest(unittest.TestCase):
    def test_valid_config(self):
        path = write(
            'google_api_key = "k"\nntfy_topic = "t"\n'
            '[schedule]\nstart = "06:30"\n'
            '[[routes]]\norigin = "a"\ndestination = "b"\n'
        )
        config = load_config(path)
        self.assertEqual(config.start, time(6, 30))
        self.assertEqual(config.end, time(22, 0))
        self.assertEqual(config.routes[0].name, "Ruta 1")

    def test_example_placeholders_are_rejected(self):
        with self.assertRaisesRegex(ConfigError, "google_api_key"):
            load_config(EXAMPLE)

    def test_missing_file(self):
        with self.assertRaisesRegex(ConfigError, "config.example.toml"):
            load_config(Path("/no/existe.toml"))

    def test_requires_routes(self):
        with self.assertRaisesRegex(ConfigError, "ruta"):
            load_config(write('google_api_key = "k"\nntfy_topic = "t"\n'))


if __name__ == "__main__":
    unittest.main()

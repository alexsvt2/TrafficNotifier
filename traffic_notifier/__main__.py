"""CLI: python -m traffic_notifier {check [--force] | test-notify}"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

from . import ntfy
from .check import run_check
from .config import ConfigError, load_config
from .routes_api import get_travel_time

DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "config.toml"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="traffic_notifier")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check", help="revisa las rutas y notifica")
    check.add_argument("--force", action="store_true", help="ignora el horario")
    commands.add_parser("test-notify", help="manda un push de prueba")
    args = parser.parse_args(argv)

    try:
        config = load_config(args.config)
        now = datetime.now()
        if args.command == "test-notify":
            ntfy.send(config.ntfy_topic, "TrafficNotifier", "Prueba: las notificaciones funcionan ✅",
                      server=config.ntfy_server)
            log("Push de prueba enviado.")
        elif run_check(config, now, get_travel_time, ntfy.send, force=args.force):
            log(f"Revisadas {len(config.routes)} ruta(s) y notificado.")
        else:
            log("Fuera del horario; no se revisó.")
    except (ConfigError, ntfy.NotifyError) as e:
        log(f"ERROR: {e}")
        return 1
    return 0


def log(message: str) -> None:
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {message}", flush=True)


if __name__ == "__main__":
    sys.exit(main())

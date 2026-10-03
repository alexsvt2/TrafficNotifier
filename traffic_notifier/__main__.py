"""CLI: python -m traffic_notifier {serve | check [--force] | test-notify | validate | remote ...}"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

from . import ntfy, static_map
from .check import MapSnapshots, run_check
from .config import ConfigError, load_config
from .daemon import serve
from .routes_api import get_traffic_path, get_travel_time

DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "config.toml"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="traffic_notifier")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("serve", help="queda corriendo: revisa cada intervalo y atiende el comando por ntfy")
    check = commands.add_parser("check", help="revisa las rutas y notifica")
    check.add_argument("--force", action="store_true", help="ignora el horario")
    commands.add_parser("test-notify", help="manda un push de prueba")
    commands.add_parser("validate", help="revisa que config.toml sea válido")
    remote = commands.add_parser("remote", help="manda un comando al proceso que está corriendo, por ntfy")
    remote.add_argument("action", choices=("check", "stop", "start"))
    args = parser.parse_args(argv)

    try:
        if args.command == "serve":
            serve(args.config, log)
        config = load_config(args.config)
        now = datetime.now()
        if args.command == "validate":
            log("config.toml es válido.")
        elif args.command == "remote":
            keyword = {"check": config.keyword, "stop": config.stop_keyword, "start": config.start_keyword}
            # Prioridad mínima: el comando no debe sonar en los celulares suscritos.
            ntfy.send(config.ntfy_topic, "TrafficNotifier", keyword[args.action], priority=1,
                      server=config.ntfy_server)
            log(f"Comando '{keyword[args.action]}' enviado.")
        elif args.command == "test-notify":
            ntfy.send(config.ntfy_topic, "TrafficNotifier", "Prueba: las notificaciones funcionan ✅",
                      server=config.ntfy_server)
            log("Push de prueba enviado.")
        elif run_check(config, now, get_travel_time, ntfy.send, force=args.force,
                       snapshot=MapSnapshots(get_traffic_path, static_map.render)):
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

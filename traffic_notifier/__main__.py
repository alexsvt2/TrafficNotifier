"""CLI: python -m traffic_notifier {serve | check [--force] | test-notify | validate | remote ...
| show | place ... | route ... | set ...}"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from . import config_edit, ntfy, static_map
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
    show = commands.add_parser("show", help="muestra la configuración (sin la API key)")
    show.add_argument("--json", action="store_true", help="salida para programas")
    place = commands.add_parser("place", help="lugares con etiqueta, para armar rutas").add_subparsers(
        dest="action", required=True)
    place.add_parser("list")
    add = place.add_parser("add", help="agrega o actualiza un lugar")
    add.add_argument("label")
    add.add_argument("where", help='"lat,lng", dirección o link de Google Maps')
    place.add_parser("remove").add_argument("label")
    route = commands.add_parser("route", help="rutas que se revisan").add_subparsers(dest="action", required=True)
    route.add_parser("list")
    add = route.add_parser("add")
    add.add_argument("origin", help="etiqueta de un lugar, dirección o lat,lng")
    add.add_argument("destination")
    add.add_argument("--name", help="nombre en la notificación (por defecto, Origen → Destino)")
    add.add_argument("--round-trip", action="store_true", help="agrega también el regreso")
    route.add_parser("remove").add_argument("number", type=int, help="número según 'route list'")
    set_ = commands.add_parser("set", help="cambia un ajuste, p. ej. set schedule.interval_minutes 25")
    set_.add_argument("setting")
    set_.add_argument("value")
    args = parser.parse_args(argv)

    try:
        if args.command in ("show", "place", "route", "set"):
            return _manage(args)
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


def _manage(args) -> int:
    """Consulta o cambia config.toml. El servicio aplica los cambios solo."""
    action = getattr(args, "action", None)
    if args.command == "set":
        config_edit.edit(args.config, lambda raw: config_edit.set_value(raw, args.setting, args.value))
        print(f"{args.setting} = {args.value}")
    elif args.command == "place" and action == "add":
        config_edit.edit(args.config, lambda raw: config_edit.add_place(raw, args.label, args.where))
        print(f"Lugar '{args.label}' guardado.")
    elif args.command == "place" and action == "remove":
        config_edit.edit(args.config, lambda raw: config_edit.remove_place(raw, args.label))
        print(f"Lugar '{args.label}' quitado.")
    elif args.command == "route" and action == "add":
        config_edit.edit(args.config, lambda raw: config_edit.add_route(
            raw, args.origin, args.destination, args.name, args.round_trip))
        print("Ruta agregada." if not args.round_trip else "Ruta de ida y vuelta agregada.")
    elif args.command == "route" and action == "remove":
        config_edit.edit(args.config, lambda raw: config_edit.remove_route(raw, args.number))
        print(f"Ruta #{args.number} quitada.")

    raw = config_edit.public(config_edit.read_raw(args.config))
    if getattr(args, "json", False):
        print(json.dumps(raw, ensure_ascii=False, indent=2))
        return 0
    if args.command in ("show", "set"):
        for section in ("schedule", "command", "thresholds", "map"):
            for key, value in raw.get(section, {}).items():
                print(f"{section}.{key} = {value}")
        for key in ("ntfy_topic", "ntfy_server"):
            if key in raw:
                print(f"{key} = {raw[key]}")
    if args.command in ("show", "place"):
        print("Lugares:")
        for label, where in raw.get("places", {}).items():
            print(f"  {label}: {where}")
    if args.command in ("show", "route"):
        print("Rutas:")
        for number, route in enumerate(load_config(args.config).routes, 1):
            print(f"  {number}. {route.name}")
    return 0


def log(message: str) -> None:
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {message}", flush=True)


if __name__ == "__main__":
    sys.exit(main())

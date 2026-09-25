# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is
A background job that checks driving times for configured routes with Google Routes API (`TRAFFIC_AWARE`) and sends one ntfy push per run. On macOS, launchd runs it every :00 and :30. The script itself skips runs outside the `[schedule]` window in `config.toml`.

## Commands
Use `/opt/homebrew/bin/python3.13`: the system Python is 3.9, and the code needs `tomllib` (3.11+). The project is stdlib only, with no venv or dependencies.

```bash
/opt/homebrew/bin/python3.13 -m unittest discover tests                  # all tests
/opt/homebrew/bin/python3.13 -m unittest tests.test_check.RunCheckTest.test_force_ignores_window  # one test
/opt/homebrew/bin/python3.13 -m traffic_notifier check [--force]         # real run (needs config.toml)
/opt/homebrew/bin/python3.13 -m traffic_notifier test-notify
./scripts/install.sh / ./scripts/uninstall.sh                            # launchd agent
```

## Architecture
The design follows the deep-module vocabulary of the `codebase-design` skill. Each module hides one external concern behind a small interface:

- `routes_api.get_travel_time(origin, dest, key) -> TravelTime`: all Google Routes HTTP details, including the field mask, parsing of `"123s"` durations, and handling of `lat,lng` versus address input. Every failure becomes a `TrafficError`.
- `ntfy.send(...)`: the ntfy POST. Title, priority and tags go in query params, not headers, because headers can't reliably carry accents or emoji.
- `config.load_config(path) -> Config`: TOML parsing plus validation. Every user-facing config problem becomes a `ConfigError`.
- `check.run_check(config, now, get_travel_time, send, force)` is the orchestrator: time window, delay classification (`duration / staticDuration` against the `moderate`/`heavy` thresholds), message formatting. Its two network dependencies are injected parameters, which is the test seam: `tests/test_check.py` passes fakes and never touches the network.

One route failing must not block the others. Failures appear as ⚠️ lines in the same notification.

`config.toml` holds secrets (API key, ntfy topic) and is gitignored. `config.example.toml` is the template, and a test checks that its placeholders are rejected. launchd runs `bin/TrafficNotifier` (a zsh wrapper that execs `$PYTHON -m traffic_notifier`) so macOS shows "TrafficNotifier" in Login Items instead of "python3.13". `launchd/*.plist` is a template: `install.sh` substitutes `__PYTHON__`, `__REPO__` and `__LOG__`. Logs go to `~/Library/Logs/TrafficNotifier.log`.

User-facing text (messages, errors, README) is in Spanish.

import argparse
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path

_LOG_FILE = None


def _strip_quotes(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        os.environ[key] = _strip_quotes(value)


def setup_file_log(app_root: Path) -> None:
    global _LOG_FILE
    log_dir = app_root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    _LOG_FILE = log_dir / "backend_service.log"


def log(message: str) -> None:
    line = f"[{datetime.now().isoformat(timespec='seconds')}] [backend] {message}"
    print(line, flush=True)
    if _LOG_FILE is not None:
        with _LOG_FILE.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")


def log_traceback() -> None:
    text = traceback.format_exc()
    print(text, flush=True)
    if _LOG_FILE is not None:
        with _LOG_FILE.open("a", encoding="utf-8") as fh:
            fh.write(text + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run TechTracker Django backend via Waitress.")
    parser.add_argument("--app-root", required=True)
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", default=None)
    args = parser.parse_args()

    app_root = Path(args.app_root).resolve()
    setup_file_log(app_root)
    log("backend runner invoked")

    env_path = app_root / ".env.local"
    load_env_file(env_path)
    log(f"env_file={env_path} exists={env_path.exists()}")

    host = args.host or os.environ.get("TECHTRACKER_BACKEND_HOST") or "0.0.0.0"
    port_value = args.port or os.environ.get("TECHTRACKER_BACKEND_PORT") or "8000"

    os.chdir(app_root)
    if str(app_root) not in sys.path:
        sys.path.insert(0, str(app_root))

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "TechTracker_django.settings")

    log(f"app_root={app_root}")
    log(f"python={sys.executable}")
    log(f"listen={host}:{port_value}")
    log(f"settings={os.environ.get('DJANGO_SETTINGS_MODULE')}")
    log(f"allowed_hosts={os.environ.get('DJANGO_ALLOWED_HOSTS', '')}")
    log(f"db={os.environ.get('DB_HOST', '')}:{os.environ.get('DB_PORT', '')}/{os.environ.get('DB_NAME', '')}")

    try:
        port = int(port_value)
        if port < 1 or port > 65535:
            raise ValueError("port must be in 1..65535")
    except Exception as exc:
        log(f"invalid port: {port_value}: {exc}")
        return 2

    try:
        import django
        from django.conf import settings
        from django.core.checks import run_checks
        from django.urls import resolve

        django.setup()
        import inventory_api.urls as inventory_urls
        import inventory_api.views as inventory_views

        log(f"settings_base_dir={getattr(settings, 'BASE_DIR', '')}")
        log(f"app_version={getattr(settings, 'APP_VERSION', '')}")
        log(f"inventory_api.urls={getattr(inventory_urls, '__file__', '')}")
        log(f"inventory_api.views={getattr(inventory_views, '__file__', '')}")
        for route in (
            "/api/agent-installer/",
            "/api/installers/agent/",
            "/api/agents/",
            "/api/agents/metric-catalog/",
            "/api/application-updates/agent-installer/",
        ):
            try:
                match = resolve(route)
                log(f"route_ok {route} -> {match.view_name}")
            except Exception as exc:
                log(f"route_missing {route}: {exc}")

        errors = run_checks()
        if errors:
            log(f"django checks returned {len(errors)} issue(s)")
            for err in errors:
                log(str(err))
        else:
            log("django checks passed")
    except Exception:
        log("django startup failed")
        log_traceback()
        return 1

    try:
        from waitress import serve
        from TechTracker_django.wsgi import application

        log("waitress starting")
        serve(application, host=host, port=port, threads=8)
        log("waitress stopped")
        return 0
    except Exception:
        log("waitress failed")
        log_traceback()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

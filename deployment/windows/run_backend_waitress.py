import argparse
import os
import sys
import traceback
from datetime import datetime
from pathlib import Path


def log(message: str) -> None:
    print(f"[{datetime.now().isoformat(timespec='seconds')}] [backend] {message}", flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run TechTracker Django backend via Waitress.")
    parser.add_argument("--app-root", required=True)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", default="8000")
    args = parser.parse_args()

    app_root = Path(args.app_root).resolve()
    os.chdir(app_root)
    if str(app_root) not in sys.path:
        sys.path.insert(0, str(app_root))

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "TechTracker_django.settings")

    log(f"app_root={app_root}")
    log(f"python={sys.executable}")
    log(f"listen={args.host}:{args.port}")
    log(f"settings={os.environ.get('DJANGO_SETTINGS_MODULE')}")
    log(f"allowed_hosts={os.environ.get('DJANGO_ALLOWED_HOSTS', '')}")
    log(f"db={os.environ.get('DB_HOST', '')}:{os.environ.get('DB_PORT', '')}/{os.environ.get('DB_NAME', '')}")

    try:
        port = int(args.port)
        if port < 1 or port > 65535:
            raise ValueError("port must be in 1..65535")
    except Exception as exc:
        log(f"invalid port: {args.port}: {exc}")
        return 2

    try:
        import django
        from django.core.checks import run_checks

        django.setup()
        errors = run_checks()
        if errors:
            log(f"django checks returned {len(errors)} issue(s)")
            for err in errors:
                log(str(err))
        else:
            log("django checks passed")
    except Exception:
        log("django startup failed")
        traceback.print_exc()
        return 1

    try:
        from waitress import serve
        from TechTracker_django.wsgi import application

        log("waitress starting")
        serve(application, host=args.host, port=port)
        log("waitress stopped")
        return 0
    except Exception:
        log("waitress failed")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

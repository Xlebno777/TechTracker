import logging
import os
import sys
import threading

from django.db import close_old_connections, connection

from .network_map_builder import build_network_map_snapshot


logger = logging.getLogger(__name__)

_started = False
_start_lock = threading.Lock()
_stop_event = threading.Event()


def _env_bool(name, default='0'):
    value = os.environ.get(name, default)
    return str(value).strip().lower() in ('1', 'true', 'yes', 'on')


def _env_int(name, default):
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _should_start_scheduler():
    if not _env_bool('NETWORK_MAP_AUTOSTART', '1'):
        return False

    if len(sys.argv) >= 2 and sys.argv[0].endswith('manage.py'):
        cmd = sys.argv[1]
        if cmd != 'runserver':
            return False
        if os.environ.get('RUN_MAIN') != 'true':
            return False
    return True


def _with_pg_advisory_lock(lock_key, callback):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_try_advisory_lock(%s)", [lock_key])
            row = cursor.fetchone()
        locked = bool(row and row[0])
    except Exception as exc:
        logger.warning("Network map advisory lock failed, running unlocked: %s", exc)
        return callback()

    if not locked:
        return None

    try:
        return callback()
    finally:
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s)", [lock_key])
        except Exception as exc:
            logger.warning("Network map advisory unlock failed: %s", exc)


def _scheduler_loop(interval_sec, lock_key, window_hours, keep_last):
    logger.info(
        "Network map scheduler started (interval=%ss, lock_key=%s, window_hours=%s, keep_last=%s)",
        interval_sec,
        lock_key,
        window_hours,
        keep_last,
    )
    while not _stop_event.is_set():
        try:
            close_old_connections()
            payload = _with_pg_advisory_lock(
                lock_key,
                lambda: build_network_map_snapshot(window_hours=window_hours, keep_last=keep_last),
            )
            if payload is None:
                logger.debug("Network map tick skipped: lock is held by another process")
            elif payload.get('status') != 'ok':
                logger.warning("Network map tick failed: %s", payload.get('error') or 'unknown error')
            else:
                logger.debug(
                    "Network map tick: snapshot_id=%s nodes=%s edges=%s duration_ms=%s",
                    payload.get('snapshot_id'),
                    payload.get('node_count'),
                    payload.get('edge_count'),
                    payload.get('build_duration_ms'),
                )
        except Exception as exc:
            logger.exception("Network map scheduler tick error: %s", exc)
        finally:
            close_old_connections()
        _stop_event.wait(max(10, interval_sec))


def start_network_map_scheduler():
    global _started
    with _start_lock:
        if _started:
            return
        if not _should_start_scheduler():
            logger.debug("Network map scheduler not started in this process")
            return

        interval_sec = max(30, _env_int('NETWORK_MAP_AUTO_INTERVAL_SEC', 300))
        lock_key = _env_int('NETWORK_MAP_LOCK_KEY', 4829138)
        window_hours = _env_int('NETWORK_MAP_WINDOW_HOURS', 24)
        keep_last = _env_int('NETWORK_MAP_KEEP_LAST', 720)

        worker = threading.Thread(
            target=_scheduler_loop,
            args=(interval_sec, lock_key, window_hours, keep_last),
            daemon=True,
            name='network-map-scheduler',
        )
        worker.start()
        _started = True

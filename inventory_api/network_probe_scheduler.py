import logging
import os
import sys
import threading

from django.db import connection
from django.db import close_old_connections

from .network_probe import run_network_probe


logger = logging.getLogger(__name__)

_started = False
_start_lock = threading.Lock()
_stop_event = threading.Event()


def _env_bool(name, default='0'):
    value = os.environ.get(name, default)
    return str(value).strip().lower() in ('1', 'true', 'yes', 'on')


def _should_start_scheduler():
    if not _env_bool('NETWORK_PROBE_AUTOSTART', '1'):
        return False

    if len(sys.argv) >= 2 and sys.argv[0].endswith('manage.py'):
        cmd = sys.argv[1]
        # Do not run background probe in non-server management commands.
        if cmd != 'runserver':
            return False
        # In Django autoreload parent process do not start.
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
        logger.warning("Network probe advisory lock failed, running unlocked: %s", exc)
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
            logger.warning("Network probe advisory unlock failed: %s", exc)


def _scheduler_loop(interval_sec, lock_key):
    logger.info("Network probe scheduler started (interval=%ss, lock_key=%s)", interval_sec, lock_key)
    while not _stop_event.is_set():
        try:
            close_old_connections()
            stats = _with_pg_advisory_lock(
                lock_key,
                lambda: run_network_probe(save_metrics=True, respect_interval=True),
            )
            if stats is None:
                logger.debug("Network probe tick skipped: lock is held by another process")
            else:
                logger.debug(
                    "Network probe tick: checked=%s skipped=%s interval_skipped=%s up=%s down=%s metrics=%s",
                    stats['checked'],
                    stats['skipped'],
                    stats['interval_skipped'],
                    stats['up'],
                    stats['down'],
                    stats['metrics_created'],
                )
        except Exception as exc:
            logger.exception("Network probe scheduler tick error: %s", exc)
        finally:
            close_old_connections()
        _stop_event.wait(max(5, interval_sec))


def start_network_probe_scheduler():
    global _started
    with _start_lock:
        if _started:
            return
        if not _should_start_scheduler():
            logger.debug("Network probe scheduler not started in this process")
            return

        interval_sec = int(os.environ.get('NETWORK_PROBE_AUTO_INTERVAL_SEC', '60'))
        lock_key = int(os.environ.get('NETWORK_PROBE_LOCK_KEY', '4829137'))

        worker = threading.Thread(
            target=_scheduler_loop,
            args=(interval_sec, lock_key),
            daemon=True,
            name='network-probe-scheduler',
        )
        worker.start()
        _started = True


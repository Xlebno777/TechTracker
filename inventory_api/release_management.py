import json
import os
import platform
import subprocess
import sys
from pathlib import Path
from urllib.request import Request, urlopen

from django.conf import settings
from django.utils import timezone

from .models import ApplicationUpdateJob


def _safe_text(value, default=""):
    text = str(value if value is not None else "").strip()
    return text or default


def _read_json_from_url(url: str, timeout: float = 10.0):
    raw_url = _safe_text(url)
    if not raw_url:
        raise ValueError("APP_RELEASE_MANIFEST_URL is not configured")
    if raw_url.startswith("file://"):
        path = Path(raw_url[7:]).expanduser()
        return json.loads(path.read_text(encoding="utf-8"))
    if "://" not in raw_url:
        path = Path(raw_url).expanduser()
        return json.loads(path.read_text(encoding="utf-8"))
    req = Request(raw_url, headers={"Accept": "application/json"})
    with urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _parse_version(version: str):
    text = _safe_text(version, "0.0.0").lower().lstrip("v")
    base = text.split("+", 1)[0].split("-", 1)[0]
    parts = []
    for chunk in base.split("."):
        try:
            parts.append(int(chunk))
        except ValueError:
            parts.append(0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def compare_versions(left: str, right: str) -> int:
    left_tuple = _parse_version(left)
    right_tuple = _parse_version(right)
    if left_tuple < right_tuple:
        return -1
    if left_tuple > right_tuple:
        return 1
    return 0


def _git_value(args):
    try:
        return subprocess.check_output(
            ["git", *args],
            cwd=str(settings.BASE_DIR),
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=3,
        ).strip()
    except Exception:
        return ""


def get_current_release_info() -> dict:
    script_path = Path(getattr(settings, "APP_UPDATE_SCRIPT", "") or "").expanduser()
    manifest_url = _safe_text(getattr(settings, "APP_RELEASE_MANIFEST_URL", ""))
    return {
        "current_version": _safe_text(getattr(settings, "APP_VERSION", ""), "0.1.0"),
        "release_channel": _safe_text(getattr(settings, "APP_RELEASE_CHANNEL", ""), "single"),
        "manifest_url": manifest_url,
        "manifest_configured": bool(manifest_url),
        "update_enabled": bool(getattr(settings, "APP_UPDATE_ENABLED", False)),
        "update_script": str(script_path),
        "update_script_exists": script_path.exists(),
        "update_workdir": str(getattr(settings, "APP_UPDATE_WORKDIR", settings.BASE_DIR)),
        "platform": platform.platform(),
        "python": sys.executable,
        "git_commit": _git_value(["rev-parse", "--short", "HEAD"]),
        "git_branch": _git_value(["branch", "--show-current"]),
    }


def normalize_manifest(raw_manifest: dict) -> dict:
    manifest = dict(raw_manifest or {})
    notes = manifest.get("notes") or manifest.get("release_notes") or []
    if isinstance(notes, str):
        notes = [notes]
    if not isinstance(notes, list):
        notes = []
    return {
        "version": _safe_text(manifest.get("version") or manifest.get("tag") or manifest.get("name")),
        "channel": _safe_text(manifest.get("channel"), _safe_text(getattr(settings, "APP_RELEASE_CHANNEL", ""), "single")),
        "release_date": _safe_text(manifest.get("release_date")),
        "git_ref": _safe_text(manifest.get("git_ref") or manifest.get("tag")),
        "download_url": _safe_text(manifest.get("download_url")),
        "sha256": _safe_text(manifest.get("sha256")),
        "notes": notes,
        "raw": manifest,
    }


def check_for_update(manifest_url: str | None = None) -> dict:
    current = get_current_release_info()
    url = _safe_text(manifest_url, current["manifest_url"])
    manifest = normalize_manifest(_read_json_from_url(url))
    latest_version = manifest["version"]
    update_available = bool(latest_version) and compare_versions(current["current_version"], latest_version) < 0
    return {
        **current,
        "latest_version": latest_version,
        "update_available": update_available,
        "manifest": manifest,
    }


def append_job_log(job: ApplicationUpdateJob, message: str):
    stamp = timezone.now().strftime("%Y-%m-%d %H:%M:%S")
    job.log = ((job.log or "") + f"[{stamp}] {message}\n")[-50000:]
    job.save(update_fields=["log", "updated_at"])


def launch_update_worker(job: ApplicationUpdateJob) -> int:
    manage_py = Path(settings.BASE_DIR) / "manage.py"
    command = [sys.executable, str(manage_py), "run_application_update", "--job-id", str(job.id)]
    creationflags = 0
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "DETACHED_PROCESS", 0)
    process = subprocess.Popen(
        command,
        cwd=str(settings.BASE_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
        close_fds=os.name != "nt",
        creationflags=creationflags,
    )
    job.pid = process.pid
    job.save(update_fields=["pid", "updated_at"])
    return process.pid


def run_update_job(job_id: int) -> ApplicationUpdateJob:
    job = ApplicationUpdateJob.objects.get(id=job_id)
    if not bool(getattr(settings, "APP_UPDATE_ENABLED", False)):
        job.status = "skipped"
        job.error = "APP_UPDATE_ENABLED=0. Обновление из интерфейса выключено."
        job.finished_at = timezone.now()
        job.save(update_fields=["status", "error", "finished_at", "updated_at"])
        append_job_log(job, job.error)
        return job

    script = Path(getattr(settings, "APP_UPDATE_SCRIPT", "") or "").expanduser()
    if not script.exists():
        job.status = "failed"
        job.error = f"Скрипт обновления не найден: {script}"
        job.finished_at = timezone.now()
        job.save(update_fields=["status", "error", "finished_at", "updated_at"])
        append_job_log(job, job.error)
        return job

    workdir = Path(getattr(settings, "APP_UPDATE_WORKDIR", settings.BASE_DIR)).expanduser()
    shell = "powershell.exe" if os.name == "nt" else "pwsh"
    command = [
        shell,
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        "-AppRoot",
        str(workdir),
        "-JobId",
        str(job.id),
    ]
    if job.git_ref:
        command.extend(["-GitRef", job.git_ref])
    if job.target_version:
        command.extend(["-TargetVersion", job.target_version])

    env = os.environ.copy()
    env.update({
        "TECHTRACKER_UPDATE_JOB_ID": str(job.id),
        "TECHTRACKER_TARGET_VERSION": job.target_version or "",
        "TECHTRACKER_TARGET_REF": job.git_ref or "",
        "TECHTRACKER_MANIFEST_URL": job.manifest_url or "",
        "TECHTRACKER_APP_ROOT": str(workdir),
    })

    job.status = "running"
    job.started_at = timezone.now()
    job.save(update_fields=["status", "started_at", "updated_at"])
    append_job_log(job, "Запуск скрипта обновления.")

    try:
        completed = subprocess.run(
            command,
            cwd=str(workdir),
            env=env,
            capture_output=True,
            text=True,
            timeout=int(getattr(settings, "APP_UPDATE_TIMEOUT_SEC", 3600)),
        )
        output = "\n".join(part for part in [completed.stdout, completed.stderr] if part)
        job.log = ((job.log or "") + output)[-50000:]
        job.finished_at = timezone.now()
        if completed.returncode == 0:
            job.status = "completed"
            job.error = ""
        else:
            job.status = "failed"
            job.error = f"Скрипт обновления завершился с кодом {completed.returncode}."
        job.save(update_fields=["status", "log", "error", "finished_at", "updated_at"])
    except Exception as exc:
        job.status = "failed"
        job.error = str(exc)
        job.finished_at = timezone.now()
        job.save(update_fields=["status", "error", "finished_at", "updated_at"])
        append_job_log(job, f"Ошибка выполнения: {exc}")
    return job

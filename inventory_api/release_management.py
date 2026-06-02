import json
import os
import platform
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

from django.conf import settings
from django.utils import timezone

from .models import ApplicationUpdateJob


DEFAULT_RELEASE_MANIFEST_URL = "https://api.github.com/repos/Xlebno777/TechTracker/releases/latest"
DEFAULT_AGENT_RELEASE_URL = "https://api.github.com/repos/Xlebno777/tracker-agent/releases/latest"
DEFAULT_AGENT_INSTALLER_ASSET = "TechTrackerAgentInstaller.exe"
DEFAULT_AGENT_INSTALLER_VERSION = "0.2.0"
DEFAULT_SYSTEM_RELEASE_VERSION = "0.1.24"


def _safe_text(value, default=""):
    text = str(value if value is not None else "").strip()
    return text or default


def _read_json_from_url(url: str, timeout: float = 10.0, github_token: str | None = None):
    raw_url = _safe_text(url)
    if not raw_url:
        raise ValueError("APP_RELEASE_MANIFEST_URL is not configured")
    if raw_url.startswith("file://"):
        path = Path(raw_url[7:]).expanduser()
        if not path.exists() and path.name == "release_manifest.json":
            fallback = path.with_name("release_manifest.example.json")
            if fallback.exists():
                path = fallback
        return json.loads(path.read_text(encoding="utf-8"))
    if "://" not in raw_url:
        path = Path(raw_url).expanduser()
        if not path.exists() and path.name == "release_manifest.json":
            fallback = path.with_name("release_manifest.example.json")
            if fallback.exists():
                path = fallback
        return json.loads(path.read_text(encoding="utf-8"))
    headers = {"Accept": "application/json", "User-Agent": "TechTracker"}
    host = urlsplit(raw_url).netloc.lower()
    if github_token and (host == "github.com" or host.endswith(".github.com")):
        headers["Authorization"] = f"Bearer {github_token}"
        headers["X-GitHub-Api-Version"] = "2022-11-28"
    req = Request(raw_url, headers=headers)
    with urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _github_repo_from_release_url(url: str):
    parsed = urlsplit(_safe_text(url))
    host = parsed.netloc.lower()
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if host == "api.github.com" and len(parts) >= 5 and parts[0] == "repos" and parts[3] == "releases":
        return parts[1], parts[2]
    if (host == "github.com" or host.endswith(".github.com")) and len(parts) >= 4 and parts[2] == "releases":
        return parts[0], parts[1]
    return None


def _github_latest_tag_from_html(url: str, fallback_tag: str):
    repo = _github_repo_from_release_url(url)
    if not repo:
        return None
    owner, repo_name = repo
    latest_html_url = f"https://github.com/{owner}/{repo_name}/releases/latest"
    html_url = latest_html_url
    try:
        req = Request(latest_html_url, headers={"User-Agent": "TechTracker"})
        with urlopen(req, timeout=10) as response:
            html_url = response.geturl()
    except Exception:
        html_url = f"https://github.com/{owner}/{repo_name}/releases/tag/{fallback_tag}"

    marker = "/releases/tag/"
    tag_name = ""
    if marker in html_url:
        tag_name = html_url.split(marker, 1)[1].split("?", 1)[0].split("#", 1)[0].strip("/")
    if not tag_name:
        tag_name = fallback_tag
        html_url = f"https://github.com/{owner}/{repo_name}/releases/tag/{tag_name}"
    return owner, repo_name, tag_name, html_url, latest_html_url


def _github_asset_size(download_url: str):
    try:
        req = Request(download_url, headers={"User-Agent": "TechTracker"}, method="HEAD")
        with urlopen(req, timeout=10) as response:
            return int(response.headers.get("Content-Length") or 0)
    except Exception:
        return 0


def _github_latest_release_fallback(url: str, asset_name: str, api_error: Exception) -> dict | None:
    latest = _github_latest_tag_from_html(url, f"v{DEFAULT_AGENT_INSTALLER_VERSION}")
    if not latest:
        return None
    owner, repo_name, tag_name, html_url, latest_html_url = latest
    quoted_asset = quote(asset_name)
    download_url = f"https://github.com/{owner}/{repo_name}/releases/download/{tag_name}/{quoted_asset}"
    size_bytes = _github_asset_size(download_url)

    return {
        "release_url": url,
        "connected": True,
        "status": "ok",
        "latest_version": tag_name.lstrip("v"),
        "tag_name": tag_name,
        "published_at": "",
        "html_url": html_url,
        "installer_asset_name": asset_name,
        "download_url": download_url,
        "size_bytes": size_bytes,
        "detail": (
            "GitHub API latest release недоступен, использован fallback через "
            f"{latest_html_url}. Ошибка API: {api_error}"
        ),
    }


def _system_release_manifest_fallback(url: str, api_error: Exception) -> dict | None:
    latest = _github_latest_tag_from_html(url, f"v{DEFAULT_SYSTEM_RELEASE_VERSION}")
    if not latest:
        return None
    owner, repo_name, tag_name, html_url, latest_html_url = latest
    version = tag_name.lstrip("v")
    asset_name = f"TechTracker-v{version}-windows-server.zip"
    download_url = f"https://github.com/{owner}/{repo_name}/releases/download/{tag_name}/{quote(asset_name)}"
    size_bytes = _github_asset_size(download_url)
    return {
        "version": version,
        "tag_name": tag_name,
        "name": f"TechTracker {tag_name}",
        "channel": "single",
        "published_at": "",
        "html_url": html_url,
        "body": (
            "GitHub API latest release недоступен, использован fallback через "
            f"{latest_html_url}. Ошибка API: {api_error}"
        ),
        "assets": [
            {
                "name": asset_name,
                "browser_download_url": download_url,
                "size": size_bytes,
            }
        ],
    }


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


def _version_file_value():
    try:
        return (Path(settings.BASE_DIR) / "VERSION").read_text(encoding="utf-8").strip()
    except Exception:
        return ""


def _effective_current_version():
    env_version = _safe_text(getattr(settings, "APP_VERSION", ""), "0.1.0")
    file_version = _safe_text(_version_file_value())
    if file_version and compare_versions(env_version, file_version) < 0:
        return file_version
    return env_version


def get_current_release_info() -> dict:
    script_path = Path(getattr(settings, "APP_UPDATE_SCRIPT", "") or "").expanduser()
    manifest_url = _safe_text(getattr(settings, "APP_RELEASE_MANIFEST_URL", ""), DEFAULT_RELEASE_MANIFEST_URL)
    env_version = _safe_text(getattr(settings, "APP_VERSION", ""), "0.1.0")
    file_version = _safe_text(_version_file_value())
    return {
        "current_version": _effective_current_version(),
        "configured_version": env_version,
        "version_file": file_version,
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
    notes = manifest.get("notes") or manifest.get("release_notes") or manifest.get("body") or []
    if isinstance(notes, str):
        notes = [line.strip("- ").strip() for line in notes.splitlines() if line.strip()]
    if not isinstance(notes, list):
        notes = []
    assets = manifest.get("assets") if isinstance(manifest.get("assets"), list) else []
    windows_asset = next(
        (
            asset for asset in assets
            if isinstance(asset, dict) and str(asset.get("name") or "").endswith("-windows-server.zip")
        ),
        {},
    )
    digest = _safe_text(windows_asset.get("digest") if isinstance(windows_asset, dict) else "")
    sha256 = _safe_text(manifest.get("sha256"))
    if not sha256 and digest.startswith("sha256:"):
        sha256 = digest.split(":", 1)[1]
    download_url = _safe_text(manifest.get("download_url"))
    if not download_url and isinstance(windows_asset, dict):
        download_url = _safe_text(windows_asset.get("browser_download_url"))
    return {
        "version": _safe_text(manifest.get("version") or manifest.get("tag") or manifest.get("tag_name") or manifest.get("name")),
        "channel": _safe_text(manifest.get("channel"), _safe_text(getattr(settings, "APP_RELEASE_CHANNEL", ""), "single")),
        "release_date": _safe_text(manifest.get("release_date") or manifest.get("published_at") or manifest.get("created_at")),
        "git_ref": _safe_text(manifest.get("git_ref") or manifest.get("tag") or manifest.get("tag_name")),
        "download_url": download_url,
        "sha256": sha256,
        "notes": notes,
        "raw": manifest,
    }


def check_for_update(manifest_url: str | None = None) -> dict:
    current = get_current_release_info()
    url = _safe_text(manifest_url, current["manifest_url"])
    github_token = os.environ.get("APP_RELEASE_GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    try:
        raw_manifest = _read_json_from_url(url, github_token=github_token)
    except Exception as exc:
        raw_manifest = _system_release_manifest_fallback(url, exc)
        if raw_manifest is None:
            raise
    manifest = normalize_manifest(raw_manifest)
    latest_version = manifest["version"]
    update_available = bool(latest_version) and compare_versions(current["current_version"], latest_version) < 0
    return {
        **current,
        "latest_version": latest_version,
        "update_available": update_available,
        "manifest": manifest,
    }


def check_agent_installer_release(release_url: str | None = None) -> dict:
    configured_url = os.environ.get("AGENT_RELEASE_URL") or os.environ.get("AGENT_RELEASE_MANIFEST_URL")
    url = _safe_text(release_url, configured_url or DEFAULT_AGENT_RELEASE_URL)
    asset_name = _safe_text(os.environ.get("AGENT_INSTALLER_ASSET_NAME"), DEFAULT_AGENT_INSTALLER_ASSET)
    payload = {
        "release_url": url,
        "connected": False,
        "status": "error",
        "latest_version": "",
        "tag_name": "",
        "published_at": "",
        "html_url": "",
        "installer_asset_name": asset_name,
        "download_url": "",
        "size_bytes": 0,
        "detail": "",
    }
    try:
        github_token = os.environ.get("AGENT_RELEASE_GITHUB_TOKEN") or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        release = _read_json_from_url(url, github_token=github_token)
    except Exception as exc:
        fallback = _github_latest_release_fallback(url, asset_name, exc)
        if fallback:
            return fallback
        payload["detail"] = str(exc)
        return payload

    assets = release.get("assets") if isinstance(release.get("assets"), list) else []
    installer_asset = next(
        (
            asset for asset in assets
            if isinstance(asset, dict) and str(asset.get("name") or "") == asset_name
        ),
        None,
    )
    if installer_asset is None:
        installer_asset = next(
            (
                asset for asset in assets
                if isinstance(asset, dict)
                and str(asset.get("name") or "").lower().endswith(".exe")
                and "installer" in str(asset.get("name") or "").lower()
            ),
            None,
        )

    tag_name = _safe_text(release.get("tag_name") or release.get("tag") or release.get("name"))
    payload.update({
        "connected": True,
        "status": "ok" if installer_asset else "missing_asset",
        "latest_version": tag_name.lstrip("v"),
        "tag_name": tag_name,
        "published_at": _safe_text(release.get("published_at") or release.get("created_at")),
        "html_url": _safe_text(release.get("html_url")),
        "detail": "" if installer_asset else f"В последнем release не найден asset {asset_name}.",
    })
    if installer_asset:
        payload.update({
            "installer_asset_name": _safe_text(installer_asset.get("name"), asset_name),
            "download_url": _safe_text(installer_asset.get("browser_download_url") or installer_asset.get("url")),
            "size_bytes": int(installer_asset.get("size") or 0),
        })
    return payload


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

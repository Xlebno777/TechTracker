from __future__ import annotations

import os
import time
from typing import Any

import requests


class LSTMRemoteClient:
    def __init__(
        self,
        *,
        base_url: str,
        api_token: str = "",
        timeout_sec: float = 20.0,
        verify_ssl: bool = True,
    ):
        self.base_url = (base_url or "").strip().rstrip("/")
        self.api_token = (api_token or "").strip()
        self.timeout_sec = float(timeout_sec)
        self.verify_ssl = bool(verify_ssl)
        if not self.base_url:
            raise RuntimeError("LSTM remote base URL is empty")
        # LSTM service is typically reached over local VPN/Tailscale addresses.
        # We disable proxy/env inheritance so requests don't get sent to an
        # unrelated corporate or desktop proxy and hang on private IP ranges.
        self.session = requests.Session()
        self.session.trust_env = False

    @classmethod
    def from_env(cls):
        base_url = os.environ.get("LSTM_REMOTE_API_BASE_URL", "http://127.0.0.1:8099")
        api_token = os.environ.get("LSTM_REMOTE_API_TOKEN", "")
        timeout_raw = os.environ.get("LSTM_REMOTE_TIMEOUT_SEC", "20")
        verify_raw = os.environ.get("LSTM_REMOTE_VERIFY_SSL", "0")
        try:
            timeout_sec = float(timeout_raw)
        except (TypeError, ValueError):
            timeout_sec = 20.0
        verify_ssl = str(verify_raw).strip().lower() in ("1", "true", "yes", "on")
        return cls(
            base_url=base_url,
            api_token=api_token,
            timeout_sec=timeout_sec,
            verify_ssl=verify_ssl,
        )

    def _headers(self):
        headers = {"Content-Type": "application/json"}
        if self.api_token:
            headers["X-API-Key"] = self.api_token
        return headers

    def check_health(self):
        url = f"{self.base_url}/health"
        try:
            response = self.session.get(
                url,
                timeout=self.timeout_sec,
                verify=self.verify_ssl,
            )
            response.raise_for_status()
            payload = response.json()
            if payload.get("status") != "ok":
                raise RuntimeError(f"Unexpected health payload: {payload}")
            return payload
        except Exception as exc:
            raise RuntimeError(f"LSTM remote health check failed: {exc}") from exc

    def submit_job(self, payload: dict[str, Any]):
        url = f"{self.base_url}/v1/jobs"
        try:
            response = self.session.post(
                url,
                json=payload,
                headers=self._headers(),
                timeout=self.timeout_sec,
                verify=self.verify_ssl,
            )
            if response.status_code >= 400:
                detail = response.text[:800]
                raise RuntimeError(f"HTTP {response.status_code}: {detail}")
            data = response.json()
            job_id = data.get("job_id")
            if not job_id:
                raise RuntimeError(f"Invalid submit response: {data}")
            return data
        except Exception as exc:
            raise RuntimeError(f"LSTM remote submit failed: {exc}") from exc

    def get_job(self, job_id: str):
        url = f"{self.base_url}/v1/jobs/{job_id}"
        try:
            response = self.session.get(
                url,
                headers=self._headers(),
                timeout=self.timeout_sec,
                verify=self.verify_ssl,
            )
            if response.status_code >= 400:
                detail = response.text[:800]
                raise RuntimeError(f"HTTP {response.status_code}: {detail}")
            return response.json()
        except Exception as exc:
            raise RuntimeError(f"LSTM remote job fetch failed: {exc}") from exc

    def wait_for_terminal(
        self,
        *,
        job_id: str,
        poll_interval_sec: float = 2.0,
        max_wait_sec: float = 120.0,
    ):
        poll_interval = max(0.5, float(poll_interval_sec))
        max_wait = max(1.0, float(max_wait_sec))

        started = time.monotonic()
        last_payload = None

        while (time.monotonic() - started) <= max_wait:
            payload = self.get_job(job_id)
            last_payload = payload
            status = str(payload.get("status", "")).strip().lower()
            if status in ("completed", "failed"):
                return payload
            time.sleep(poll_interval)

        if last_payload is None:
            last_payload = {"job_id": job_id, "status": "timeout"}
        else:
            last_payload = dict(last_payload)
            last_payload["status"] = "timeout"
        return last_payload

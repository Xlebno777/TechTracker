from __future__ import annotations

from fastapi import Depends, FastAPI, Header, HTTPException, status

from .config import settings
from .job_runner import registry
from .schemas import ForecastRequest, JobCreateResponse, JobStatusResponse

app = FastAPI(title="TechTracker LSTM Remote", version="0.1.0")


def require_api_key(x_api_key: str | None = Header(default=None)):
    token = (settings.api_token or "").strip()
    if not token:
        return
    if (x_api_key or "").strip() != token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")


@app.get("/health")
def health():
    return {"status": "ok", "service": "lstm_remote", "version": app.version}


@app.post("/v1/jobs", response_model=JobCreateResponse)
def create_job(payload: ForecastRequest, _: None = Depends(require_api_key)):
    if not payload.metrics:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Metrics payload is empty")
    job_id = registry.submit(payload)
    return JobCreateResponse(job_id=job_id, status="queued")


@app.get("/v1/jobs/{job_id}", response_model=JobStatusResponse)
def get_job(job_id: str, _: None = Depends(require_api_key)):
    row = registry.get(job_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return row

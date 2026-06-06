import hashlib
import hmac
import logging
import os

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request, status

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="GitHub SLM Reviewer", version="0.1.0")

WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")


def _verify_signature(payload: bytes, sig_header: str | None) -> None:
    if not WEBHOOK_SECRET:
        return
    if not sig_header or not sig_header.startswith("sha256="):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing signature")
    expected = "sha256=" + hmac.new(WEBHOOK_SECRET.encode(), payload, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig_header):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid signature")


@app.post("/webhook", status_code=status.HTTP_200_OK)
async def webhook(
    request: Request,
    x_hub_signature_256: str | None = Header(default=None),
    x_github_event: str | None = Header(default=None),
):
    payload = await request.body()
    _verify_signature(payload, x_hub_signature_256)

    if x_github_event != "pull_request":
        logger.info("Ignored event: %s", x_github_event)
        return {"status": "ignored", "event": x_github_event}

    body = await request.json() if not payload else __import__("json").loads(payload)
    action = body.get("action")

    if action not in ("opened", "synchronize"):
        logger.info("Ignored PR action: %s", action)
        return {"status": "ignored", "action": action}

    pr = body.get("pull_request", {})
    repo = body.get("repository", {})

    pr_number = pr.get("number")
    repo_name = repo.get("full_name")
    commit_sha = pr.get("head", {}).get("sha")

    logger.info("PR #%s | repo=%s | sha=%s | action=%s", pr_number, repo_name, commit_sha, action)

    return {"status": "ok", "pr": pr_number, "repo": repo_name, "sha": commit_sha}


@app.get("/health")
async def health():
    ollama_ok = False
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
            ollama_ok = resp.status_code == 200
    except Exception:
        pass

    return {"status": "ok", "ollama": "reachable" if ollama_ok else "unreachable"}

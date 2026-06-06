"""Smoke test: send a fake pull_request webhook and verify 200 OK."""
import hashlib
import hmac
import json
import sys

import httpx

BASE_URL = "http://localhost:8000"
WEBHOOK_SECRET = ""  # leave empty to skip signature — matches server default

FAKE_PAYLOAD = {
    "action": "opened",
    "pull_request": {
        "number": 42,
        "head": {"sha": "abc1234def5678"},
    },
    "repository": {
        "full_name": "test-owner/test-repo",
    },
}


def _signature(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_webhook():
    body = json.dumps(FAKE_PAYLOAD).encode()
    headers = {"X-GitHub-Event": "pull_request", "Content-Type": "application/json"}
    if WEBHOOK_SECRET:
        headers["X-Hub-Signature-256"] = _signature(WEBHOOK_SECRET, body)

    resp = httpx.post(f"{BASE_URL}/webhook", content=body, headers=headers)
    print(f"Status : {resp.status_code}")
    print(f"Response: {resp.json()}")

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    data = resp.json()
    assert data["status"] == "ok"
    assert data["pr"] == 42
    assert data["repo"] == "test-owner/test-repo"
    assert data["sha"] == "abc1234def5678"
    print("PASS: webhook test")


def test_health():
    resp = httpx.get(f"{BASE_URL}/health")
    print(f"Health: {resp.json()}")
    assert resp.status_code == 200
    print("PASS: health test")


if __name__ == "__main__":
    try:
        test_health()
        test_webhook()
        print("\nAll tests passed.")
    except AssertionError as exc:
        print(f"\nFAIL: {exc}", file=sys.stderr)
        sys.exit(1)
    except httpx.ConnectError:
        print("ERROR: Could not connect to server at", BASE_URL, file=sys.stderr)
        print("       Start the server first: uvicorn app.main:app --reload", file=sys.stderr)
        sys.exit(1)

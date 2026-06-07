#!/usr/bin/env python3
"""Smoke test: send a realistic signed pull_request webhook to the local server.

Usage:
    python3 scripts/smoke_test.py [base_url]

Defaults to http://localhost:8000.  The server must already be running.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import time

import httpx
from dotenv import load_dotenv

load_dotenv()

BASE_URL = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://localhost:8000"
SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "")


# ── Realistic PR webhook payload ─────────────────────────────────────────────
# The payload mimics a GitHub pull_request "opened" event.
# It does NOT contain the diff — GitHub sends diff via the API, not the webhook.
PAYLOAD = {
    "action": "opened",
    "number": 7,
    "pull_request": {
        "number": 7,
        "title": "Add user authentication module",
        "state": "open",
        "head": {
            "sha": "d4a9b2c1e8f3a7b6c5d4e3f2a1b0c9d8e7f6a5b4",
            "ref": "feature/auth",
            "label": "acme:feature/auth",
        },
        "base": {
            "sha": "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0",
            "ref": "main",
            "label": "acme:main",
        },
        "user": {"login": "dev-user", "type": "User"},
        "body": "Adds login and user lookup functions.",
        "additions": 12,
        "deletions": 3,
        "changed_files": 1,
    },
    "repository": {
        "id": 123456789,
        "name": "api",
        "full_name": "acme/api",
        "private": False,
        "owner": {"login": "acme", "type": "Organization"},
        "default_branch": "main",
    },
    "sender": {"login": "dev-user", "type": "User"},
    "installation": None,
}


def _sign(body: bytes) -> str:
    if not SECRET:
        return ""
    return "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()


def _check_health() -> bool:
    try:
        r = httpx.get(f"{BASE_URL}/health", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


def main() -> None:
    # ── Health check ─────────────────────────────────────────────────────────
    print(f"Target : {BASE_URL}")
    if not _check_health():
        print("ERROR  : Server is not reachable.  Start it first:")
        print("           bash run.sh")
        print("         or:")
        print("           python3 -m uvicorn app.main:app --reload")
        sys.exit(1)

    health = httpx.get(f"{BASE_URL}/health").json()
    print(f"Health : {health}")
    print()

    # ── Build and sign payload ────────────────────────────────────────────────
    body = json.dumps(PAYLOAD, separators=(",", ":")).encode()
    sig = _sign(body)

    headers = {
        "Content-Type": "application/json",
        "X-GitHub-Event": "pull_request",
        "X-GitHub-Delivery": "smoke-test-delivery-001",
    }
    if sig:
        headers["X-Hub-Signature-256"] = sig

    # ── Send webhook ──────────────────────────────────────────────────────────
    print(f"Sending pull_request 'opened' event (PR #{PAYLOAD['number']})...")
    if sig:
        print(f"Signature: {sig[:30]}...")
    else:
        print("Signature: (none — GITHUB_WEBHOOK_SECRET not set)")
    print()

    try:
        resp = httpx.post(f"{BASE_URL}/webhook", content=body, headers=headers, timeout=10)
    except httpx.ConnectError:
        print(f"ERROR: Could not connect to {BASE_URL}/webhook")
        sys.exit(1)

    print(f"Status  : {resp.status_code}")
    print(f"Response: {json.dumps(resp.json(), indent=2)}")
    print()

    if resp.status_code == 200:
        print("PASS: webhook accepted — review running in background")
        print()
        print("Watch server logs for:")
        print("  INFO  PR #7 | repo=acme/api | sha=d4a9b2c... | action=opened")
        print("  INFO  (review_pr will attempt GitHub API calls — expected to fail")
        print("         with a fake repo, but the flow and logging will be visible)")
    else:
        print(f"FAIL: unexpected status {resp.status_code}")
        sys.exit(1)


if __name__ == "__main__":
    main()

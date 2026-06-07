#!/usr/bin/env python3
"""Register (or update) a GitHub webhook for this reviewer.

Usage:
    python3 setup_webhook.py <webhook_url>
    python3 setup_webhook.py          # reads WEBHOOK_URL from .env

The script is idempotent: if a webhook pointing to the same URL already
exists on the repo it prints its ID and exits without creating a duplicate.
"""
from __future__ import annotations

import os
import sys

from dotenv import load_dotenv
from github import Github, GithubException

load_dotenv()


def main() -> None:
    token = os.getenv("GITHUB_TOKEN", "")
    repo_slug = os.getenv("GITHUB_REPO", "")       # owner/repo
    secret = os.getenv("GITHUB_WEBHOOK_SECRET", "")

    webhook_url = sys.argv[1] if len(sys.argv) > 1 else os.getenv("WEBHOOK_URL", "")

    # ── Validate inputs ────────────────────────────────────────────────────
    errors = []
    if not token:
        errors.append("GITHUB_TOKEN is not set")
    if not repo_slug or "/" not in repo_slug:
        errors.append("GITHUB_REPO must be set as owner/repo (e.g. acme/api)")
    if not webhook_url:
        errors.append(
            "Webhook URL is required — either pass it as an argument:\n"
            "    python3 setup_webhook.py https://<your-ngrok-id>.ngrok-free.app/webhook\n"
            "or set WEBHOOK_URL in .env"
        )
    if errors:
        for e in errors:
            print(f"ERROR: {e}")
        sys.exit(1)

    if not webhook_url.endswith("/webhook"):
        webhook_url = webhook_url.rstrip("/") + "/webhook"

    # ── Connect to GitHub ───────────────────────────────────────────────────
    g = Github(token)
    try:
        repo = g.get_repo(repo_slug)
    except GithubException as exc:
        print(f"ERROR: Could not access repo '{repo_slug}': {exc.data.get('message', exc)}")
        sys.exit(1)

    # ── Check for existing webhook on the same URL ─────────────────────────
    for hook in repo.get_hooks():
        if hook.config.get("url") == webhook_url:
            print(f"Webhook already exists  id={hook.id}  url={webhook_url}")
            return

    # ── Create webhook ──────────────────────────────────────────────────────
    config: dict = {
        "url": webhook_url,
        "content_type": "json",
    }
    if secret:
        config["secret"] = secret

    try:
        hook = repo.create_hook(
            name="web",
            config=config,
            events=["pull_request"],
            active=True,
        )
    except GithubException as exc:
        print(f"ERROR: Failed to create webhook: {exc.data.get('message', exc)}")
        sys.exit(1)

    print(f"Webhook created  id={hook.id}  url={webhook_url}")
    print(f"Events: pull_request")
    print(f"Repo:   {repo_slug}")
    if not secret:
        print("WARNING: No GITHUB_WEBHOOK_SECRET set — webhook payload is unsigned")


if __name__ == "__main__":
    main()

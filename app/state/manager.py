from __future__ import annotations

import logging
import os
from typing import Optional

from dotenv import load_dotenv
from supabase import Client, create_client

from app.state.models import Issue, PRState

load_dotenv()

logger = logging.getLogger(__name__)


class StateManager:
    def __init__(self):
        url = os.getenv("SUPABASE_URL", "")
        key = os.getenv("SUPABASE_KEY", "")
        self._sb: Client = create_client(url, key)

    # ------------------------------------------------------------------
    # PR state
    # ------------------------------------------------------------------

    def get_pr_state(self, owner: str, repo: str, pr_number: int) -> Optional[PRState]:
        result = (
            self._sb.table("pr_states")
            .select("*")
            .eq("owner", owner)
            .eq("repo", repo)
            .eq("pr_number", pr_number)
            .execute()
        )
        if not result.data:
            return None
        return PRState(**result.data[0])

    def create_pr_state(self, owner: str, repo: str, pr_number: int, sha: str) -> PRState:
        payload = {
            "owner": owner,
            "repo": repo,
            "pr_number": pr_number,
            "iteration": 0,
            "open_issues": 0,
            "resolved_issues": 0,
            "last_sha": sha,
        }
        result = self._sb.table("pr_states").insert(payload).execute()
        return PRState(**result.data[0])

    def increment_iteration(self, pr_id: str) -> None:
        result = (
            self._sb.table("pr_states")
            .select("iteration")
            .eq("pr_id", pr_id)
            .execute()
        )
        if not result.data:
            logger.warning("increment_iteration: pr_id %s not found", pr_id)
            return
        new_val = result.data[0]["iteration"] + 1
        self._sb.table("pr_states").update({"iteration": new_val}).eq("pr_id", pr_id).execute()

    # ------------------------------------------------------------------
    # Issues
    # ------------------------------------------------------------------

    def save_issue(
        self,
        pr_id: str,
        issue: dict,
        comment_id: Optional[str],
        sha: str,
    ) -> Issue:
        payload = {
            "pr_id": pr_id,
            "filename": issue["filename"],
            "line": issue["line"],
            "severity": issue["severity"],
            "category": issue["category"],
            "message": issue["message"],
            "fix": issue["fix"],
            "status": "open",
            "first_sha": sha,
            "comment_id": comment_id,
        }
        result = self._sb.table("issues").insert(payload).execute()
        return Issue(**result.data[0])

    def get_open_issues(self, pr_id: str) -> list[Issue]:
        result = (
            self._sb.table("issues")
            .select("*")
            .eq("pr_id", pr_id)
            .eq("status", "open")
            .execute()
        )
        return [Issue(**row) for row in result.data]

    def mark_issue_fixed(self, issue_id: str) -> None:
        self._sb.table("issues").update({"status": "fixed"}).eq("issue_id", issue_id).execute()

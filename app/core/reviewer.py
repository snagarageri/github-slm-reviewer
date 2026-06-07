from __future__ import annotations

import logging
from typing import Optional

from app.analysis.chunker import prepare_files_for_analysis
from app.analysis.engine import AnalysisEngine
from app.github.client import GitHubClient
from app.github.comments import format_issue_comment, format_summary_comment
from app.github.parser import extract_changed_lines, get_language
from app.state.manager import StateManager
from app.state.models import Issue

logger = logging.getLogger(__name__)

# Only review files in these languages; all others are skipped.
ALLOWED_LANGUAGES = {"Python", "JavaScript", "TypeScript", "Go", "Java"}


def _fp(filename: str, line: int, category: str) -> str:
    """Stable fingerprint for deduplicating issues across review iterations."""
    return f"{filename}:{line}:{category}"


def _to_comment_dict(issue: dict) -> dict:
    """Map engine output keys (message/fix) to comment formatter keys (title/description)."""
    return {
        **issue,
        "title": issue.get("message", issue.get("title", "Issue")),
        "description": issue.get("fix", issue.get("description", "")),
    }


class CodeReviewer:
    def __init__(self) -> None:
        self._github = GitHubClient()
        self._engine = AnalysisEngine()
        self._state = StateManager()

    async def review_pr(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        commit_sha: str,
    ) -> dict:
        # 1. Get or create PR state ------------------------------------------------
        pr_state = self._state.get_pr_state(owner, repo, pr_number)
        if pr_state is None:
            pr_state = self._state.create_pr_state(owner, repo, pr_number, commit_sha)

        # 2. Fetch and filter PR files --------------------------------------------
        pr_files = self._github.get_pr_files(owner, repo, pr_number)
        prepared = [
            f for f in prepare_files_for_analysis(pr_files)
            if f["language"] in ALLOWED_LANGUAGES
        ]

        # 3. Load existing open issues and index by fingerprint -------------------
        existing_issues: list[Issue] = self._state.get_open_issues(pr_state.pr_id)
        existing_fps: dict[str, Issue] = {
            _fp(i.filename, i.line, i.category): i for i in existing_issues
        }

        # 4. Run analysis and compare against existing issues --------------------
        seen_fps: set[str] = set()
        new_count = skipped_count = 0
        all_new_issues: list[dict] = []

        for file_data in prepared:
            filename = file_data["filename"]
            language = file_data["language"]
            patch = file_data["patch"]

            result = self._engine.analyze_file(filename, language, patch)
            changed_lines = set(extract_changed_lines(patch))

            for issue in result.get("issues", []):
                issue_with_file = {**issue, "filename": filename}
                fingerprint = _fp(filename, issue["line"], issue["category"])
                seen_fps.add(fingerprint)

                if fingerprint in existing_fps:
                    # Already commented in a prior iteration — nothing to do.
                    skipped_count += 1
                    continue

                # New issue: post inline comment if the line is in the diff.
                comment_id: Optional[str] = None
                if issue["line"] in changed_lines:
                    try:
                        comment_id = self._github.post_review_comment(
                            owner, repo, pr_number, commit_sha,
                            filename, issue["line"],
                            format_issue_comment(_to_comment_dict(issue_with_file)),
                        )
                    except Exception as exc:
                        logger.warning(
                            "Inline comment failed for %s:%s — %s",
                            filename, issue["line"], exc,
                        )

                self._state.save_issue(pr_state.pr_id, issue_with_file, comment_id, commit_sha)
                all_new_issues.append(issue_with_file)
                new_count += 1

        # Issues that were open last run but absent this run → mark fixed.
        fixed_count = 0
        for fingerprint, existing_issue in existing_fps.items():
            if fingerprint not in seen_fps:
                self._state.mark_issue_fixed(existing_issue.issue_id)
                fixed_count += 1

        # 5. Build and post PR summary comment -----------------------------------
        still_open = [
            _to_comment_dict({
                "filename": i.filename,
                "line": i.line,
                "severity": i.severity,
                "category": i.category,
                "message": i.message,
                "fix": i.fix,
            })
            for fp, i in existing_fps.items()
            if fp in seen_fps
        ]
        summary_issues = [_to_comment_dict(i) for i in all_new_issues] + still_open
        iteration = pr_state.iteration + 1
        self._github.post_pr_comment(
            owner, repo, pr_number,
            format_summary_comment(iteration, summary_issues),
        )

        # 6. Bump iteration counter ----------------------------------------------
        self._state.increment_iteration(pr_state.pr_id)

        return {
            "pr": pr_number,
            "iteration": iteration,
            "new": new_count,
            "skipped": skipped_count,
            "fixed": fixed_count,
        }

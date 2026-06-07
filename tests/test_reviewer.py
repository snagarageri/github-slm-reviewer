"""Tests for CodeReviewer — all external clients are mocked."""
from __future__ import annotations

import asyncio
import sys
import os
import traceback
from types import SimpleNamespace
from unittest.mock import MagicMock, call

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.core.reviewer import CodeReviewer, _fp
from app.state.models import Issue, PRState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run(coro):
    return asyncio.run(coro)


# A patch where lines 1-5 are all changed (added), so any issue on those
# lines will be eligible for an inline comment.
SAMPLE_PATCH = (
    "@@ -0,0 +1,5 @@\n"
    "+import os\n"
    "+\n"
    "+def login(user, pw):\n"
    "+    query = f\"SELECT * FROM users WHERE user='{user}'\"\n"
    "+    return db.execute(query)\n"
)

def _pr_file(filename: str = "auth.py", patch: str = SAMPLE_PATCH):
    return SimpleNamespace(filename=filename, patch=patch, additions=5, deletions=0, status="added")


def _issue(line: int = 4, severity: str = "critical", category: str = "security",
           message: str = "SQL injection", fix: str = "Use parameterised queries") -> dict:
    return {"line": line, "severity": severity, "category": category,
            "message": message, "fix": fix}


def _existing_issue(filename: str = "auth.py", line: int = 4,
                    category: str = "security") -> Issue:
    return Issue(
        issue_id="issue-existing-1",
        pr_id="pr-uuid-1",
        filename=filename,
        line=line,
        severity="critical",
        category=category,
        message="SQL injection",
        fix="Use parameterised queries",
        status="open",
        first_sha="old-sha",
    )


def _pr_state(iteration: int = 0) -> PRState:
    return PRState(
        pr_id="pr-uuid-1",
        owner="acme",
        repo="api",
        pr_number=42,
        iteration=iteration,
        open_issues=0,
        resolved_issues=0,
        last_sha="sha-prev",
    )


def _make_reviewer(
    pr_state_exists: bool = True,
    pr_files: list | None = None,
    analysis_issues: list | None = None,
    open_issues: list | None = None,
) -> CodeReviewer:
    rv = CodeReviewer.__new__(CodeReviewer)

    rv._github = MagicMock()
    rv._github.get_pr_files.return_value = pr_files if pr_files is not None else [_pr_file()]
    rv._github.post_review_comment.return_value = "gh-comment-42"
    rv._github.post_pr_comment.return_value = None

    rv._engine = MagicMock()
    rv._engine.analyze_file.return_value = {
        "issues": analysis_issues if analysis_issues is not None else [_issue()],
        "overall_score": 60,
        "summary": "Security issues found",
    }

    existing = open_issues if open_issues is not None else []
    rv._state = MagicMock()
    rv._state.get_pr_state.return_value = _pr_state() if pr_state_exists else None
    rv._state.create_pr_state.return_value = _pr_state()
    rv._state.get_open_issues.return_value = existing
    rv._state.save_issue.return_value = None
    rv._state.mark_issue_fixed.return_value = None
    rv._state.increment_iteration.return_value = None

    return rv


# ---------------------------------------------------------------------------
# New issue → inline comment + saved to state
# ---------------------------------------------------------------------------

def test_new_issue_posts_inline_comment():
    rv = _make_reviewer(open_issues=[])
    run(rv.review_pr("acme", "api", 42, "sha-new"))
    rv._github.post_review_comment.assert_called_once()
    args = rv._github.post_review_comment.call_args[0]
    assert args[0] == "acme"    # owner
    assert args[1] == "api"     # repo
    assert args[2] == 42        # pr_number
    assert args[3] == "sha-new" # commit_sha
    assert args[4] == "auth.py" # path
    assert args[5] == 4         # line


def test_new_issue_saved_to_supabase():
    rv = _make_reviewer(open_issues=[])
    run(rv.review_pr("acme", "api", 42, "sha-new"))
    rv._state.save_issue.assert_called_once()
    _, issue_dict, comment_id, sha = rv._state.save_issue.call_args[0]
    assert issue_dict["filename"] == "auth.py"
    assert issue_dict["line"] == 4
    assert issue_dict["severity"] == "critical"
    assert sha == "sha-new"


def test_new_issue_returns_correct_counts():
    rv = _make_reviewer(open_issues=[])
    result = run(rv.review_pr("acme", "api", 42, "sha-new"))
    assert result["new"] == 1
    assert result["skipped"] == 0
    assert result["fixed"] == 0


# ---------------------------------------------------------------------------
# Already-open issue → skip (no new comment, no new DB row)
# ---------------------------------------------------------------------------

def test_existing_open_issue_is_skipped():
    existing = [_existing_issue()]  # same file:line:category as _issue()
    rv = _make_reviewer(open_issues=existing)
    run(rv.review_pr("acme", "api", 42, "sha-new"))
    rv._github.post_review_comment.assert_not_called()
    rv._state.save_issue.assert_not_called()


def test_existing_open_issue_skipped_count():
    existing = [_existing_issue()]
    rv = _make_reviewer(open_issues=existing)
    result = run(rv.review_pr("acme", "api", 42, "sha-new"))
    assert result["skipped"] == 1
    assert result["new"] == 0


# ---------------------------------------------------------------------------
# Issue gone from new run → mark fixed
# ---------------------------------------------------------------------------

def test_resolved_issue_is_marked_fixed():
    existing = [_existing_issue()]   # open issue from last run
    rv = _make_reviewer(open_issues=existing, analysis_issues=[])  # engine finds nothing
    run(rv.review_pr("acme", "api", 42, "sha-new"))
    rv._state.mark_issue_fixed.assert_called_once_with("issue-existing-1")


def test_resolved_issue_fixed_count():
    existing = [_existing_issue()]
    rv = _make_reviewer(open_issues=existing, analysis_issues=[])
    result = run(rv.review_pr("acme", "api", 42, "sha-new"))
    assert result["fixed"] == 1
    assert result["new"] == 0


def test_no_false_fix_when_issue_still_present():
    existing = [_existing_issue()]   # issue still found in new run too
    rv = _make_reviewer(open_issues=existing, analysis_issues=[_issue()])
    run(rv.review_pr("acme", "api", 42, "sha-new"))
    rv._state.mark_issue_fixed.assert_not_called()


# ---------------------------------------------------------------------------
# Summary comment is always posted
# ---------------------------------------------------------------------------

def test_summary_posted_with_new_issues():
    rv = _make_reviewer(open_issues=[])
    run(rv.review_pr("acme", "api", 42, "sha-new"))
    rv._github.post_pr_comment.assert_called_once()
    body = rv._github.post_pr_comment.call_args[0][3]
    assert "SLM Review" in body


def test_summary_posted_with_no_issues():
    rv = _make_reviewer(open_issues=[], analysis_issues=[])
    run(rv.review_pr("acme", "api", 42, "sha-new"))
    rv._github.post_pr_comment.assert_called_once()
    body = rv._github.post_pr_comment.call_args[0][3]
    assert "No issues found" in body


def test_summary_posted_after_fix():
    existing = [_existing_issue()]
    rv = _make_reviewer(open_issues=existing, analysis_issues=[])
    run(rv.review_pr("acme", "api", 42, "sha-new"))
    rv._github.post_pr_comment.assert_called_once()


def test_summary_contains_iteration_number():
    rv = _make_reviewer(pr_state_exists=True, open_issues=[])
    run(rv.review_pr("acme", "api", 42, "sha-new"))
    body = rv._github.post_pr_comment.call_args[0][3]
    assert "Iteration 1" in body  # pr_state.iteration=0 → iteration=1


# ---------------------------------------------------------------------------
# PR state management
# ---------------------------------------------------------------------------

def test_creates_state_when_none_exists():
    rv = _make_reviewer(pr_state_exists=False, open_issues=[])
    run(rv.review_pr("acme", "api", 42, "sha-new"))
    rv._state.create_pr_state.assert_called_once_with("acme", "api", 42, "sha-new")


def test_does_not_create_state_when_exists():
    rv = _make_reviewer(pr_state_exists=True, open_issues=[])
    run(rv.review_pr("acme", "api", 42, "sha-new"))
    rv._state.create_pr_state.assert_not_called()


def test_increments_iteration_always():
    rv = _make_reviewer(open_issues=[], analysis_issues=[])
    run(rv.review_pr("acme", "api", 42, "sha-new"))
    rv._state.increment_iteration.assert_called_once_with("pr-uuid-1")


# ---------------------------------------------------------------------------
# Language filtering
# ---------------------------------------------------------------------------

def test_skips_non_target_language_file():
    rust_file = _pr_file(filename="lib.rs", patch=SAMPLE_PATCH)
    rv = _make_reviewer(pr_files=[rust_file], open_issues=[])
    run(rv.review_pr("acme", "api", 42, "sha-new"))
    rv._engine.analyze_file.assert_not_called()


def test_reviews_target_language_files():
    files = [
        _pr_file("app.py"),
        _pr_file("index.ts"),
        _pr_file("main.go"),
    ]
    rv = _make_reviewer(pr_files=files, open_issues=[], analysis_issues=[])
    run(rv.review_pr("acme", "api", 42, "sha-new"))
    assert rv._engine.analyze_file.call_count == 3


def test_skips_file_with_no_patch():
    no_patch = SimpleNamespace(filename="deleted.py", patch=None,
                               additions=0, deletions=10, status="removed")
    rv = _make_reviewer(pr_files=[no_patch], open_issues=[])
    run(rv.review_pr("acme", "api", 42, "sha-new"))
    rv._engine.analyze_file.assert_not_called()


# ---------------------------------------------------------------------------
# Inline comment only on diff lines
# ---------------------------------------------------------------------------

def test_no_inline_comment_for_line_outside_diff():
    # Issue on line 99 which is NOT in SAMPLE_PATCH (only lines 1-5 changed)
    rv = _make_reviewer(open_issues=[], analysis_issues=[_issue(line=99)])
    run(rv.review_pr("acme", "api", 42, "sha-new"))
    rv._github.post_review_comment.assert_not_called()
    # But the issue should still be saved to Supabase
    rv._state.save_issue.assert_called_once()


# ---------------------------------------------------------------------------
# Fingerprint helper
# ---------------------------------------------------------------------------

def test_fp_is_stable():
    assert _fp("auth.py", 4, "security") == _fp("auth.py", 4, "security")


def test_fp_differs_by_field():
    assert _fp("auth.py", 4, "security") != _fp("auth.py", 5, "security")
    assert _fp("auth.py", 4, "security") != _fp("auth.py", 4, "bug")
    assert _fp("auth.py", 4, "security") != _fp("other.py", 4, "security")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    passed = failed = 0
    for fn in tests:
        try:
            fn()
            print(f"  PASS  {fn.__name__}")
            passed += 1
        except Exception:
            print(f"  FAIL  {fn.__name__}")
            traceback.print_exc()
            failed += 1

    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)

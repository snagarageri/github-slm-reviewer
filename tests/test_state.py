"""Tests for app/state — all Supabase calls are mocked."""
from __future__ import annotations

import sys
import os
import traceback
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.state.models import Issue, PRState
from app.state.manager import StateManager


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------

def _chain(data: list) -> MagicMock:
    """Return a chainable Supabase query mock whose .execute() returns data."""
    execute_result = MagicMock()
    execute_result.data = data

    chain = MagicMock()
    # Every builder method returns the same chain so calls can be chained freely.
    for method in ("select", "eq", "insert", "update"):
        getattr(chain, method).return_value = chain
    chain.execute.return_value = execute_result
    return chain


def _manager(table_side_effect) -> StateManager:
    """Build a StateManager whose _sb.table() uses the given side_effect."""
    mgr = StateManager.__new__(StateManager)
    mgr._sb = MagicMock()
    mgr._sb.table.side_effect = table_side_effect
    return mgr


# Canonical row shapes returned by Supabase
PR_ROW = {
    "pr_id": "pr-uuid-1",
    "owner": "acme",
    "repo": "api",
    "pr_number": 7,
    "iteration": 0,
    "open_issues": 0,
    "resolved_issues": 0,
    "last_sha": "abc123",
}

ISSUE_ROW = {
    "issue_id": "issue-uuid-1",
    "pr_id": "pr-uuid-1",
    "filename": "app/auth.py",
    "line": 12,
    "severity": "critical",
    "category": "security",
    "message": "SQL injection",
    "fix": "Use parameterised queries",
    "status": "open",
    "first_sha": "abc123",
    "comment_id": "gh-comment-99",
}


# ---------------------------------------------------------------------------
# get_pr_state
# ---------------------------------------------------------------------------

def test_get_pr_state_returns_none_when_not_found():
    mgr = _manager([_chain([])])
    result = mgr.get_pr_state("acme", "api", 7)
    assert result is None


def test_get_pr_state_returns_pr_state_object():
    mgr = _manager([_chain([PR_ROW])])
    result = mgr.get_pr_state("acme", "api", 7)
    assert isinstance(result, PRState)
    assert result.pr_id == "pr-uuid-1"
    assert result.owner == "acme"
    assert result.repo == "api"
    assert result.pr_number == 7
    assert result.last_sha == "abc123"


def test_get_pr_state_queries_correct_table():
    chain = _chain([PR_ROW])
    mgr = _manager([chain])
    mgr.get_pr_state("acme", "api", 7)
    mgr._sb.table.assert_called_once_with("pr_states")


# ---------------------------------------------------------------------------
# create_pr_state
# ---------------------------------------------------------------------------

def test_create_pr_state_returns_pr_state_object():
    mgr = _manager([_chain([PR_ROW])])
    result = mgr.create_pr_state("acme", "api", 7, "abc123")
    assert isinstance(result, PRState)
    assert result.pr_id == "pr-uuid-1"


def test_create_pr_state_builds_correct_payload():
    chain = _chain([PR_ROW])
    mgr = _manager([chain])
    mgr.create_pr_state("acme", "api", 7, "abc123")

    call_args = chain.insert.call_args[0][0]
    assert call_args["owner"] == "acme"
    assert call_args["repo"] == "api"
    assert call_args["pr_number"] == 7
    assert call_args["last_sha"] == "abc123"
    assert call_args["iteration"] == 0
    assert call_args["open_issues"] == 0
    assert call_args["resolved_issues"] == 0
    # pr_id must NOT be in payload — database generates it
    assert "pr_id" not in call_args


# ---------------------------------------------------------------------------
# save_issue
# ---------------------------------------------------------------------------

ISSUE_DICT = {
    "filename": "app/auth.py",
    "line": 12,
    "severity": "critical",
    "category": "security",
    "message": "SQL injection",
    "fix": "Use parameterised queries",
}


def test_save_issue_returns_issue_object():
    mgr = _manager([_chain([ISSUE_ROW])])
    result = mgr.save_issue("pr-uuid-1", ISSUE_DICT, "gh-comment-99", "abc123")
    assert isinstance(result, Issue)
    assert result.issue_id == "issue-uuid-1"
    assert result.status == "open"


def test_save_issue_stores_correct_fields():
    chain = _chain([ISSUE_ROW])
    mgr = _manager([chain])
    mgr.save_issue("pr-uuid-1", ISSUE_DICT, "gh-comment-99", "abc123")

    payload = chain.insert.call_args[0][0]
    assert payload["pr_id"] == "pr-uuid-1"
    assert payload["filename"] == "app/auth.py"
    assert payload["line"] == 12
    assert payload["severity"] == "critical"
    assert payload["category"] == "security"
    assert payload["status"] == "open"
    assert payload["first_sha"] == "abc123"
    assert payload["comment_id"] == "gh-comment-99"


def test_save_issue_with_no_comment_id():
    row = {**ISSUE_ROW, "comment_id": None}
    chain = _chain([row])
    mgr = _manager([chain])
    result = mgr.save_issue("pr-uuid-1", ISSUE_DICT, None, "abc123")
    assert result.comment_id is None
    assert chain.insert.call_args[0][0]["comment_id"] is None


# ---------------------------------------------------------------------------
# get_open_issues
# ---------------------------------------------------------------------------

def test_get_open_issues_returns_list_of_issues():
    row2 = {**ISSUE_ROW, "issue_id": "issue-uuid-2", "line": 20}
    mgr = _manager([_chain([ISSUE_ROW, row2])])
    results = mgr.get_open_issues("pr-uuid-1")
    assert len(results) == 2
    assert all(isinstance(i, Issue) for i in results)


def test_get_open_issues_empty():
    mgr = _manager([_chain([])])
    assert mgr.get_open_issues("pr-uuid-1") == []


def test_get_open_issues_filters_by_pr_and_status():
    chain = _chain([ISSUE_ROW])
    mgr = _manager([chain])
    mgr.get_open_issues("pr-uuid-1")

    eq_calls = [call[0] for call in chain.eq.call_args_list]
    assert ("pr_id", "pr-uuid-1") in eq_calls
    assert ("status", "open") in eq_calls


# ---------------------------------------------------------------------------
# mark_issue_fixed
# ---------------------------------------------------------------------------

def test_mark_issue_fixed_calls_update():
    chain = _chain([])
    mgr = _manager([chain])
    mgr.mark_issue_fixed("issue-uuid-1")

    chain.update.assert_called_once_with({"status": "fixed"})
    eq_calls = [call[0] for call in chain.eq.call_args_list]
    assert ("issue_id", "issue-uuid-1") in eq_calls


def test_mark_issue_fixed_targets_issues_table():
    chain = _chain([])
    mgr = _manager([chain])
    mgr.mark_issue_fixed("issue-uuid-1")
    mgr._sb.table.assert_called_once_with("issues")


# ---------------------------------------------------------------------------
# increment_iteration
# ---------------------------------------------------------------------------

def test_increment_iteration_bumps_by_one():
    select_chain = _chain([{"iteration": 3}])
    update_chain = _chain([])
    mgr = _manager([select_chain, update_chain])
    mgr.increment_iteration("pr-uuid-1")

    update_chain.update.assert_called_once_with({"iteration": 4})


def test_increment_iteration_does_nothing_when_not_found():
    select_chain = _chain([])
    mgr = _manager([select_chain])
    # Should not raise
    mgr.increment_iteration("nonexistent-pr")
    # Only one table() call (the select); no update table() call
    assert mgr._sb.table.call_count == 1


def test_increment_iteration_targets_pr_states_table():
    select_chain = _chain([{"iteration": 0}])
    update_chain = _chain([])
    mgr = _manager([select_chain, update_chain])
    mgr.increment_iteration("pr-uuid-1")

    calls = [c[0][0] for c in mgr._sb.table.call_args_list]
    assert calls == ["pr_states", "pr_states"]


# ---------------------------------------------------------------------------
# Pydantic model validation
# ---------------------------------------------------------------------------

def test_issue_model_defaults():
    issue = Issue(
        issue_id="x",
        pr_id="p",
        filename="f.py",
        line=1,
        severity="warning",
        category="bug",
        message="msg",
        fix="fix",
        first_sha="sha",
    )
    assert issue.status == "open"
    assert issue.comment_id is None


def test_pr_state_model_defaults():
    state = PRState(
        pr_id="p",
        owner="o",
        repo="r",
        pr_number=1,
        last_sha="sha",
    )
    assert state.iteration == 0
    assert state.open_issues == 0
    assert state.resolved_issues == 0


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

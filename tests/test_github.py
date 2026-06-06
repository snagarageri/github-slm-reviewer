"""Tests for app/github — no real GitHub API calls."""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.github.parser import extract_changed_lines, get_language, parse_diff
from app.github.comments import format_issue_comment, format_summary_comment

# ---------------------------------------------------------------------------
# Sample unified diff used across multiple tests
# ---------------------------------------------------------------------------
SAMPLE_PATCH = """\
@@ -10,7 +10,9 @@ def foo():
     x = 1
     y = 2
-    return x
+    z = x + y
+    print(z)
+    return z

@@ -20,4 +22,4 @@ def bar():
-    old_call()
+    new_call()
     pass
"""


# ---------------------------------------------------------------------------
# parse_diff
# ---------------------------------------------------------------------------

def test_parse_diff_counts():
    records = parse_diff(SAMPLE_PATCH)
    added   = [r for r in records if r["change_type"] == "added"]
    removed = [r for r in records if r["change_type"] == "removed"]
    context = [r for r in records if r["change_type"] == "context"]
    assert len(added) == 4,   f"expected 4 added, got {len(added)}"
    assert len(removed) == 2, f"expected 2 removed, got {len(removed)}"
    assert len(context) >= 2, f"expected >=2 context, got {len(context)}"


def test_parse_diff_line_numbers():
    records = parse_diff(SAMPLE_PATCH)
    added = [r for r in records if r["change_type"] == "added"]
    # First hunk starts at new line 10; first two context lines are 10,11 → added starts at 12
    added_lines = [r["line_number"] for r in added]
    assert 12 in added_lines, f"line 12 not found in added lines: {added_lines}"
    assert 13 in added_lines
    assert 14 in added_lines


def test_parse_diff_content():
    records = parse_diff(SAMPLE_PATCH)
    added = [r for r in records if r["change_type"] == "added"]
    contents = [r["content"] for r in added]
    assert any("z = x + y" in c for c in contents)
    assert any("return z" in c for c in contents)


# ---------------------------------------------------------------------------
# extract_changed_lines
# ---------------------------------------------------------------------------

def test_extract_changed_lines_returns_only_added():
    lines = extract_changed_lines(SAMPLE_PATCH)
    assert all(isinstance(ln, int) for ln in lines)
    assert len(lines) == 4  # 3 added in hunk1 + 1 added in hunk2


def test_extract_changed_lines_no_removed():
    """extract_changed_lines must come only from 'added' records.

    Removed lines use old-file numbering; added lines use new-file numbering.
    The two spaces can overlap numerically, so we verify by change_type, not
    by comparing integers.
    """
    records = parse_diff(SAMPLE_PATCH)
    changed = set(extract_changed_lines(SAMPLE_PATCH))
    # Every returned line number must map to at least one 'added' record
    added_lines = {r["line_number"] for r in records if r["change_type"] == "added"}
    assert changed == added_lines, (
        f"extract_changed_lines returned {changed}, expected added-only set {added_lines}"
    )


# ---------------------------------------------------------------------------
# get_language
# ---------------------------------------------------------------------------

LANGUAGE_CASES = [
    ("main.py",          "Python"),
    ("src/app.ts",       "TypeScript"),
    ("index.js",         "JavaScript"),
    ("component.tsx",    "TypeScript"),
    ("component.jsx",    "JavaScript"),
    ("main.go",          "Go"),
    ("lib.rs",           "Rust"),
    ("Main.java",        "Java"),
    ("app.rb",           "Ruby"),
    ("style.css",        "CSS"),
    ("config.yaml",      "YAML"),
    ("config.yml",       "YAML"),
    ("schema.sql",       "SQL"),
    ("Dockerfile",       "Dockerfile"),
    ("makefile",         "Makefile"),
    ("unknown.xyz",      "Unknown"),
]


def test_get_language():
    for filename, expected in LANGUAGE_CASES:
        result = get_language(filename)
        assert result == expected, f"get_language({filename!r}) = {result!r}, expected {expected!r}"


# ---------------------------------------------------------------------------
# format_issue_comment
# ---------------------------------------------------------------------------

def test_format_issue_comment_critical():
    issue = {"severity": "critical", "title": "Null dereference", "description": "ptr may be None"}
    out = format_issue_comment(issue)
    assert "❌" in out
    assert "Null dereference" in out
    assert "ptr may be None" in out


def test_format_issue_comment_warning():
    issue = {"severity": "warning", "title": "Unused variable", "description": "x is never read",
             "filename": "app/main.py", "line": 42}
    out = format_issue_comment(issue)
    assert "⚠️" in out
    assert "app/main.py:42" in out


def test_format_issue_comment_suggestion():
    issue = {"severity": "suggestion", "title": "Use list comprehension"}
    out = format_issue_comment(issue)
    assert "💡" in out
    assert "Use list comprehension" in out
    assert len(out) > 0


# ---------------------------------------------------------------------------
# format_summary_comment
# ---------------------------------------------------------------------------

MOCK_ISSUES = [
    {"severity": "critical",   "title": "SQL injection",       "description": "unsanitised input"},
    {"severity": "warning",    "title": "Broad exception",     "description": "catches all exceptions"},
    {"severity": "suggestion", "title": "Add type hints",      "description": "improves readability"},
    {"severity": "warning",    "title": "Magic number",        "description": "replace 42 with constant"},
]


def test_format_summary_comment_contains_header():
    out = format_summary_comment(1, MOCK_ISSUES)
    assert "SLM Review" in out
    assert "Iteration 1" in out


def test_format_summary_comment_counts():
    out = format_summary_comment(1, MOCK_ISSUES)
    # table should show 1 critical, 2 warnings, 1 suggestion
    # they appear as the count digits in the markdown table row
    lines = out.splitlines()
    count_row = [l for l in lines if "| 1 |" in l or "| 2 |" in l]
    assert count_row, "count table row not found"


def test_format_summary_comment_all_issues_present():
    out = format_summary_comment(2, MOCK_ISSUES)
    for issue in MOCK_ISSUES:
        assert issue["title"] in out, f"title {issue['title']!r} missing from summary"


def test_format_summary_comment_empty():
    out = format_summary_comment(1, [])
    assert "No issues found" in out


def test_format_summary_comment_sorted_by_severity():
    out = format_summary_comment(1, MOCK_ISSUES)
    crit_pos = out.index("SQL injection")
    warn_pos = out.index("Broad exception")
    sugg_pos = out.index("Add type hints")
    assert crit_pos < warn_pos < sugg_pos, "issues not sorted critical→warning→suggestion"


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import traceback

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

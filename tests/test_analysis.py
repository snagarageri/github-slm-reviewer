"""Tests for app/analysis — no real Ollama calls."""
from __future__ import annotations

import json
import sys
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.analysis.chunker import chunk_patch, prepare_files_for_analysis, should_skip_file
from app.analysis.engine import AnalysisEngine
from app.analysis.prompts import build_user_prompt, SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_ollama_response(payload: dict) -> dict:
    return {"message": {"content": json.dumps(payload)}}


def _make_pr_file(filename: str, patch: str | None = "@@ -1 +1 @@\n+x = 1\n"):
    return SimpleNamespace(filename=filename, patch=patch)


# ---------------------------------------------------------------------------
# should_skip_file
# ---------------------------------------------------------------------------

SKIP_CASES = [
    ("package-lock.json",           True),
    ("yarn.lock",                   True),
    ("poetry.lock",                 True),
    ("go.sum",                      True),
    ("src/app.min.js",              True),
    ("dist/bundle.js",              True),
    ("app/migrations/0001_init.py", True),
    ("file.pyc",                    True),
    ("image.png",                   True),
    ("styles.min.css",              True),
]

KEEP_CASES = [
    ("app/main.py",                 False),
    ("src/index.ts",                False),
    ("lib/utils.go",                False),
    ("tests/test_foo.py",           False),
    ("README.md",                   False),
    ("app/models/user.py",          False),
]


def test_should_skip_file_skips():
    for filename, expected in SKIP_CASES:
        result = should_skip_file(filename)
        assert result == expected, f"should_skip_file({filename!r}) = {result}, expected {expected}"


def test_should_skip_file_keeps():
    for filename, expected in KEEP_CASES:
        result = should_skip_file(filename)
        assert result == expected, f"should_skip_file({filename!r}) = {result}, expected {expected}"


# ---------------------------------------------------------------------------
# chunk_patch
# ---------------------------------------------------------------------------

def _make_patch(num_added_lines: int) -> str:
    body = "\n".join(f"+    line_{i} = {i}" for i in range(num_added_lines))
    return f"@@ -1,0 +1,{num_added_lines} @@\n{body}\n"


def test_chunk_patch_small_returns_one_chunk():
    patch = _make_patch(20)
    chunks = chunk_patch(patch, max_lines=80)
    assert len(chunks) == 1


def test_chunk_patch_large_splits():
    patch = _make_patch(200)
    chunks = chunk_patch(patch, max_lines=80)
    assert len(chunks) > 1, "large patch should be split into multiple chunks"
    for chunk in chunks:
        assert len(chunk.splitlines()) <= 80 + 1  # +1 for repeated hunk header


def test_chunk_patch_empty():
    assert chunk_patch("") == []


def test_chunk_patch_multi_hunk_respects_boundary():
    # Two small hunks that together exceed max_lines
    hunk1 = "@@ -1,3 +1,3 @@\n" + "\n".join(f"+line_{i}" for i in range(50)) + "\n"
    hunk2 = "@@ -60,3 +60,3 @@\n" + "\n".join(f"+line_{i}" for i in range(50)) + "\n"
    patch = hunk1 + hunk2
    chunks = chunk_patch(patch, max_lines=60)
    assert len(chunks) == 2
    assert "@@ -1" in chunks[0]
    assert "@@ -60" in chunks[1]


def test_chunk_patch_reassembly_contains_all_lines():
    patch = _make_patch(150)
    chunks = chunk_patch(patch, max_lines=80)
    combined = "".join(chunks)
    for i in range(150):
        assert f"line_{i}" in combined, f"line_{i} lost after chunking"


# ---------------------------------------------------------------------------
# prepare_files_for_analysis
# ---------------------------------------------------------------------------

def test_prepare_files_filters_skippable():
    files = [
        _make_pr_file("app/main.py"),
        _make_pr_file("package-lock.json"),
        _make_pr_file("yarn.lock"),
        _make_pr_file("src/utils.ts"),
    ]
    result = prepare_files_for_analysis(files)
    names = [r["filename"] for r in result]
    assert "app/main.py" in names
    assert "src/utils.ts" in names
    assert "package-lock.json" not in names
    assert "yarn.lock" not in names


def test_prepare_files_filters_no_patch():
    files = [
        _make_pr_file("app/main.py", patch="@@ -1 +1 @@\n+x=1\n"),
        _make_pr_file("app/deleted.py", patch=None),
    ]
    result = prepare_files_for_analysis(files)
    assert len(result) == 1
    assert result[0]["filename"] == "app/main.py"


def test_prepare_files_sets_language():
    files = [_make_pr_file("app/service.go")]
    result = prepare_files_for_analysis(files)
    assert result[0]["language"] == "Go"


# ---------------------------------------------------------------------------
# build_user_prompt
# ---------------------------------------------------------------------------

def test_build_user_prompt_includes_fields():
    out = build_user_prompt("app/main.py", "Python", "@@ -1 +1 @@\n+x=1\n")
    assert "app/main.py" in out
    assert "Python" in out
    assert "+x=1" in out


def test_build_user_prompt_with_context():
    out = build_user_prompt("app/main.py", "Python", "@@ -1 +1 @@\n+x=1\n", "def foo():")
    assert "def foo():" in out


# ---------------------------------------------------------------------------
# AnalysisEngine — mocked Ollama
# ---------------------------------------------------------------------------

VALID_RESPONSE = {
    "issues": [
        {
            "line": 5,
            "severity": "critical",
            "category": "security",
            "message": "SQL injection risk",
            "fix": "Use parameterised queries",
        }
    ],
    "overall_score": 45,
    "summary": "Critical security issue detected",
}


def test_analyze_file_valid_response():
    engine = AnalysisEngine.__new__(AnalysisEngine)
    engine._model = "test-model"
    engine._client = MagicMock()
    engine._client.chat.return_value = _fake_ollama_response(VALID_RESPONSE)

    result = engine.analyze_file("app/db.py", "Python", "@@ -1 +5 @@\n+query = f'SELECT * FROM users WHERE id={uid}'\n")

    assert result["overall_score"] == 45
    assert len(result["issues"]) == 1
    assert result["issues"][0]["severity"] == "critical"
    assert result["summary"] == "Critical security issue detected"


def test_analyze_file_malformed_json_returns_empty():
    engine = AnalysisEngine.__new__(AnalysisEngine)
    engine._model = "test-model"
    engine._client = MagicMock()
    engine._client.chat.return_value = {"message": {"content": "not json at all!!"}}

    result = engine.analyze_file("app/foo.py", "Python", "@@ -1 +1 @@\n+x=1\n")

    assert result["issues"] == []
    assert result["overall_score"] == 0


def test_analyze_file_partial_json_recovered():
    """Model wraps JSON in markdown fences — engine should still parse it."""
    wrapped = "```json\n" + json.dumps(VALID_RESPONSE) + "\n```"
    engine = AnalysisEngine.__new__(AnalysisEngine)
    engine._model = "test-model"
    engine._client = MagicMock()
    engine._client.chat.return_value = {"message": {"content": wrapped}}

    result = engine.analyze_file("app/db.py", "Python", "@@ -1 +1 @@\n+x=1\n")
    assert len(result["issues"]) == 1


def test_analyze_file_ollama_exception_returns_empty():
    engine = AnalysisEngine.__new__(AnalysisEngine)
    engine._model = "test-model"
    engine._client = MagicMock()
    engine._client.chat.side_effect = RuntimeError("connection refused")

    result = engine.analyze_file("app/foo.py", "Python", "@@ -1 +1 @@\n+x=1\n")
    assert result["issues"] == []
    assert "Error" in result["summary"]


def test_analyze_file_missing_keys_defaulted():
    """Model returns JSON but omits optional keys — defaults should fill them."""
    engine = AnalysisEngine.__new__(AnalysisEngine)
    engine._model = "test-model"
    engine._client = MagicMock()
    engine._client.chat.return_value = {"message": {"content": '{"issues": []}'}}

    result = engine.analyze_file("app/foo.py", "Python", "@@ -1 +1 @@\n+x=1\n")
    assert "overall_score" in result
    assert "summary" in result


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

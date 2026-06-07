from __future__ import annotations

import re

from app.github.parser import get_language

_SKIP_PATTERNS: list[str] = [
    # dependency lock files
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "Pipfile.lock",
    "Gemfile.lock",
    "composer.lock",
    "cargo.lock",
    "go.sum",
    # minified / generated JS/CSS
    r".*\.min\.js$",
    r".*\.min\.css$",
    r".*\.bundle\.js$",
    r".*-dist\.js$",
    # database migrations (rarely need line-level review)
    r".*/migrations/.*\.py$",
    r".*/migrate/.*\.sql$",
    # build artefacts / compiled output
    r".*\.pb\.go$",
    r".*\.pb\.py$",
    r".*_pb2\.py$",
    r".*\.generated\.[a-z]+$",
    r"dist/.*",
    r"build/.*",
    r"\.next/.*",
    r"__pycache__/.*",
    # binary / image / data formats
    r".*\.(png|jpg|jpeg|gif|svg|ico|woff|woff2|ttf|eot|pdf|zip|tar|gz|bin|exe|dll|so|dylib)$",
    # changelogs and lockfiles
    r"CHANGELOG.*",
    r".*\.lock$",
]

_COMPILED_PATTERNS = [re.compile(p, re.IGNORECASE) for p in _SKIP_PATTERNS]


def should_skip_file(filename: str) -> bool:
    """Return True if the file should be excluded from analysis."""
    base = filename.split("/")[-1].lower()
    for pat in _COMPILED_PATTERNS:
        if pat.match(filename) or pat.match(base):
            return True
    # skip files with no meaningful extension that are likely generated
    if get_language(filename) == "Unknown":
        ext = base.rsplit(".", 1)[-1] if "." in base else ""
        if ext in ("map", "snap", "pyc", "pyo", "class", "o", "a"):
            return True
    return False


def chunk_patch(patch: str, max_lines: int = 80) -> list[str]:
    """Split a large unified diff patch into smaller chunks.

    Tries to split on hunk boundaries first; falls back to line-count slicing
    within a hunk if a single hunk exceeds max_lines.
    """
    if not patch:
        return []

    hunk_re = re.compile(r"^@@.*@@", re.MULTILINE)
    hunk_starts = [m.start() for m in hunk_re.finditer(patch)]

    if not hunk_starts:
        return [patch]

    # Split patch into individual hunks
    hunks: list[str] = []
    for i, start in enumerate(hunk_starts):
        end = hunk_starts[i + 1] if i + 1 < len(hunk_starts) else len(patch)
        hunks.append(patch[start:end])

    chunks: list[str] = []
    current_lines: list[str] = []
    current_count = 0

    for hunk in hunks:
        hunk_line_count = len(hunk.splitlines())

        if hunk_line_count > max_lines:
            # flush current accumulation first
            if current_lines:
                chunks.append("".join(current_lines))
                current_lines, current_count = [], 0
            # slice oversized hunk into line-count windows
            lines = hunk.splitlines(keepends=True)
            header = lines[0]
            window: list[str] = [header]
            for line in lines[1:]:
                if len(window) >= max_lines:
                    chunks.append("".join(window))
                    window = [header]  # repeat hunk header for context
                window.append(line)
            if window:
                chunks.append("".join(window))
        elif current_count + hunk_line_count > max_lines:
            chunks.append("".join(current_lines))
            current_lines = [hunk]
            current_count = hunk_line_count
        else:
            current_lines.append(hunk)
            current_count += hunk_line_count

    if current_lines:
        chunks.append("".join(current_lines))

    return chunks


def prepare_files_for_analysis(pr_files: list) -> list[dict]:
    """Filter and prepare PR files for analysis.

    Accepts a list of PRFile objects (or any object with .filename and .patch).
    Returns a list of dicts: {filename, language, patch}.
    """
    prepared = []
    for f in pr_files:
        if should_skip_file(f.filename):
            continue
        if not f.patch:
            continue
        prepared.append(
            {
                "filename": f.filename,
                "language": get_language(f.filename),
                "patch": f.patch,
            }
        )
    return prepared

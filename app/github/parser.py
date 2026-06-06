import re

_EXTENSION_MAP: dict[str, str] = {
    "py": "Python",
    "js": "JavaScript",
    "jsx": "JavaScript",
    "ts": "TypeScript",
    "tsx": "TypeScript",
    "go": "Go",
    "rs": "Rust",
    "java": "Java",
    "kt": "Kotlin",
    "rb": "Ruby",
    "php": "PHP",
    "c": "C",
    "cpp": "C++",
    "cc": "C++",
    "cxx": "C++",
    "h": "C",
    "hpp": "C++",
    "cs": "C#",
    "swift": "Swift",
    "sh": "Shell",
    "bash": "Shell",
    "zsh": "Shell",
    "yaml": "YAML",
    "yml": "YAML",
    "json": "JSON",
    "toml": "TOML",
    "md": "Markdown",
    "sql": "SQL",
    "html": "HTML",
    "css": "CSS",
    "scss": "SCSS",
    "tf": "Terraform",
    "dockerfile": "Dockerfile",
}


def parse_diff(patch: str) -> list[dict]:
    """Parse a unified diff patch into a list of line records.

    Each record: {line_number: int, content: str, change_type: 'added'|'removed'|'context'}
    line_number refers to the new-file line number for added/context lines,
    and the old-file line number for removed lines.
    """
    results: list[dict] = []
    old_line = 0
    new_line = 0

    for raw_line in patch.splitlines():
        hunk_match = re.match(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@", raw_line)
        if hunk_match:
            old_line = int(hunk_match.group(1))
            new_line = int(hunk_match.group(2))
            continue

        if raw_line.startswith("+") and not raw_line.startswith("+++"):
            results.append({"line_number": new_line, "content": raw_line[1:], "change_type": "added"})
            new_line += 1
        elif raw_line.startswith("-") and not raw_line.startswith("---"):
            results.append({"line_number": old_line, "content": raw_line[1:], "change_type": "removed"})
            old_line += 1
        else:
            # context line (or file header — skip those)
            if not raw_line.startswith("\\"):
                results.append({"line_number": new_line, "content": raw_line, "change_type": "context"})
                old_line += 1
                new_line += 1

    return results


def extract_changed_lines(patch: str) -> list[int]:
    """Return new-file line numbers for lines that were added or modified."""
    return [
        record["line_number"]
        for record in parse_diff(patch)
        if record["change_type"] == "added"
    ]


def get_language(filename: str) -> str:
    """Infer language from filename or extension."""
    basename = filename.rsplit("/", 1)[-1].lower()

    # exact filename matches
    if basename == "dockerfile":
        return "Dockerfile"
    if basename in ("makefile", "gnumakefile"):
        return "Makefile"

    ext = basename.rsplit(".", 1)[-1] if "." in basename else ""
    return _EXTENSION_MAP.get(ext, "Unknown")

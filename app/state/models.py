from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel


class Issue(BaseModel):
    issue_id: str
    pr_id: str
    filename: str
    line: int
    severity: str
    category: str
    message: str
    fix: str
    status: Literal["open", "fixed", "wont_fix"] = "open"
    first_sha: str
    comment_id: Optional[str] = None


class PRState(BaseModel):
    pr_id: str
    owner: str
    repo: str
    pr_number: int
    iteration: int = 0
    open_issues: int = 0
    resolved_issues: int = 0
    last_sha: str

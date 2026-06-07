from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv
from github import Github, GithubException

load_dotenv()


@dataclass
class PRFile:
    filename: str
    patch: str | None
    additions: int
    deletions: int
    status: str


@dataclass
class PRInfo:
    title: str
    author: str
    base_branch: str
    head_sha: str
    number: int


class GitHubClient:
    def __init__(self, token: str | None = None):
        self._token = token or os.getenv("GITHUB_TOKEN", "")
        self._gh = Github(self._token)

    def _repo(self, owner: str, repo: str):
        return self._gh.get_repo(f"{owner}/{repo}")

    def get_pr_files(self, owner: str, repo: str, pr_number: int) -> list[PRFile]:
        pr = self._repo(owner, repo).get_pull(pr_number)
        return [
            PRFile(
                filename=f.filename,
                patch=f.patch,
                additions=f.additions,
                deletions=f.deletions,
                status=f.status,
            )
            for f in pr.get_files()
        ]

    def get_pr_info(self, owner: str, repo: str, pr_number: int) -> PRInfo:
        pr = self._repo(owner, repo).get_pull(pr_number)
        return PRInfo(
            title=pr.title,
            author=pr.user.login,
            base_branch=pr.base.ref,
            head_sha=pr.head.sha,
            number=pr.number,
        )

    def post_review_comment(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        commit_sha: str,
        path: str,
        line: int,
        body: str,
    ) -> str | None:
        repo_obj = self._repo(owner, repo)
        pr = repo_obj.get_pull(pr_number)
        commit = repo_obj.get_commit(commit_sha)
        comment = pr.create_review_comment(body=body, commit=commit, path=path, line=line)
        return str(comment.id)

    def post_pr_comment(self, owner: str, repo: str, pr_number: int, body: str) -> None:
        pr = self._repo(owner, repo).get_pull(pr_number)
        pr.create_issue_comment(body)

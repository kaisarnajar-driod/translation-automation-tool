"""Git operations: clone, commit, stage, diff."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from git import GitCommandError, InvalidGitRepositoryError, Repo

logger = logging.getLogger(__name__)


class GitError(Exception):
    """Raised when a git operation fails."""


@dataclass
class CommitResult:
    sha: str


class GitService:
    """Wraps GitPython for repository operations."""

    def __init__(self, repo_path: str | Path) -> None:
        self._path = Path(repo_path)
        self._repo: Repo | None = None

    @property
    def repo(self) -> Repo:
        if self._repo is None:
            try:
                self._repo = Repo(self._path)
            except InvalidGitRepositoryError as exc:
                raise GitError(f"Not a valid git repository: {self._path}") from exc
        return self._repo

    @classmethod
    def clone(cls, url: str, dest: str | Path, branch: str = "main") -> GitService:
        dest = Path(dest)
        if dest.exists() and any(dest.iterdir()):
            logger.info("Directory %s already exists, opening as repo", dest)
            svc = cls(dest)
            _ = svc.repo
            return svc
        logger.info("Cloning %s → %s (branch=%s)", url, dest, branch)
        try:
            Repo.clone_from(url, str(dest), branch=branch)
        except GitCommandError as exc:
            raise GitError(f"Clone failed: {exc}") from exc
        return cls(dest)

    def stage_files(self, paths: list[str | Path]) -> None:
        str_paths = [str(p) for p in paths]
        self.repo.index.add(str_paths)

    def commit(self, message: str) -> CommitResult:
        logger.info("Committing: %s", message)
        try:
            commit = self.repo.index.commit(message)
            return CommitResult(sha=commit.hexsha)
        except GitCommandError as exc:
            raise GitError(f"Commit failed: {exc}") from exc

    def get_file_content_at_commit(self, filepath: str, commit: str = "HEAD~1") -> str | None:
        """Return the content of a file at a given commit, or None if it didn't exist."""
        try:
            return self.repo.git.show(f"{commit}:{filepath}")
        except GitCommandError:
            return None

"""Git operations: clone, pull, push, commit, stage."""

from __future__ import annotations

import logging
import re
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
            current_url = svc.repo.remotes.origin.url
            if current_url != url:
                logger.info("Updating origin URL: %s → %s", current_url, url)
                svc.repo.remotes.origin.set_url(url)
            return svc
        logger.info("Cloning %s → %s (branch=%s)", url, dest, branch)
        try:
            Repo.clone_from(url, str(dest), branch=branch)
        except GitCommandError as exc:
            raise GitError(f"Clone failed: {exc}") from exc
        return cls(dest)

    def pull(self, branch: str | None = None) -> None:
        """Pull latest changes from the remote for the given (or current) branch."""
        try:
            origin = self.repo.remotes.origin
            target = branch or self.repo.active_branch.name
            logger.info("Pulling latest changes from origin/%s", target)
            origin.pull(target)
        except GitCommandError as exc:
            raise GitError(f"Pull failed: {exc}") from exc

    def push(self, branch: str | None = None) -> None:
        """Push committed changes to the remote."""
        try:
            origin = self.repo.remotes.origin
            target = branch or self.repo.active_branch.name
            logger.info("Pushing to origin/%s", target)
            origin.push(target)
        except GitCommandError as exc:
            raise GitError(f"Push failed: {exc}") from exc

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

    @staticmethod
    def repo_name_from_url(url: str) -> str:
        """Extract a filesystem-safe repo name from a git URL.

        Works with GitHub, Bitbucket, GitLab, and any Git hosting provider.

        Examples:
          https://github.com/org/my-app.git      -> org_my-app
          git@github.com:org/my-app.git           -> org_my-app
          git@bitbucket.org:team/project.git      -> team_project
          https://gitlab.com/group/repo.git       -> group_repo
        """
        url = url.rstrip("/")
        if url.endswith(".git"):
            url = url[:-4]

        # SSH: git@host:org/repo
        ssh_match = re.search(r":([^/]+)/(.+)$", url)
        if ssh_match and "://" not in url:
            return f"{ssh_match.group(1)}_{ssh_match.group(2)}"

        # HTTPS: https://host/org/repo
        parts = url.rstrip("/").split("/")
        if len(parts) >= 2:
            return f"{parts[-2]}_{parts[-1]}"

        return parts[-1] if parts else "repo"

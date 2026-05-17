from __future__ import annotations

import contextlib
import os
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from git import InvalidGitRepositoryError, Repo

from .models import Repository, RepositorySourceType


GITHUB_RE = re.compile(r"^https://github\.com/(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+?)(?:\.git)?/?$")


@dataclass(frozen=True)
class PreparedWorkspace:
    repository: Repository
    workspace_path: Path
    commit_hash: str
    default_branch: str


def validate_public_github_url(url: str) -> tuple[str, str]:
    match = GITHUB_RE.match(url.strip())
    if not match:
        raise ValidationError("Only public GitHub repository URLs are supported.")
    return match.group("owner"), match.group("repo")


def normalize_local_path(path: str) -> Path:
    resolved = Path(path).expanduser().resolve()
    if not resolved.exists():
        raise ValidationError("Local repository path does not exist.")
    if not any(resolved == root or root in resolved.parents for root in settings.SAFE_LOCAL_REPO_ROOTS):
        raise ValidationError("Local repository path is outside configured safe roots.")
    return resolved


def extract_commit_hash(path: Path) -> str:
    try:
        repo = Repo(path, search_parent_directories=True)
    except InvalidGitRepositoryError:
        return ""
    return repo.head.commit.hexsha


def extract_default_branch(path: Path) -> str:
    try:
        repo = Repo(path)
    except InvalidGitRepositoryError:
        return ""
    with contextlib.suppress(TypeError, ValueError, AttributeError):
        return repo.active_branch.name
    with contextlib.suppress(IndexError):
        return repo.git.symbolic_ref("refs/remotes/origin/HEAD").split("/")[-1]
    return ""


class RepositoryPreparationService:
    def __init__(self) -> None:
        settings.REPO_CACHE_ROOT.mkdir(parents=True, exist_ok=True)

    def prepare(self, source_type: str, repo_url: str = "", local_path: str = "") -> PreparedWorkspace:
        if source_type == RepositorySourceType.GITHUB:
            return self._prepare_github(repo_url)
        if source_type == RepositorySourceType.LOCAL:
            return self._prepare_local(local_path)
        raise ValidationError("Unsupported repository source type.")

    def _prepare_github(self, repo_url: str) -> PreparedWorkspace:
        owner, repo_name = validate_public_github_url(repo_url)
        identity_hash = Repository.build_identity_hash(RepositorySourceType.GITHUB, url=repo_url)
        workspace_path = settings.REPO_CACHE_ROOT / identity_hash

        with self._lock(identity_hash):
            if not workspace_path.exists():
                self._shallow_clone(repo_url, workspace_path)

            default_branch = extract_default_branch(workspace_path)
            commit_hash = extract_commit_hash(workspace_path)
            repository, _ = Repository.objects.update_or_create(
                identity_hash=identity_hash,
                defaults={
                    "source_type": RepositorySourceType.GITHUB,
                    "url": repo_url,
                    "name": repo_name,
                    "default_branch": default_branch,
                    "local_path": str(workspace_path),
                    "commit_hash": commit_hash,
                    "indexed_at": timezone.now(),
                },
            )
        return PreparedWorkspace(repository=repository, workspace_path=workspace_path, commit_hash=commit_hash, default_branch=default_branch)

    def _prepare_local(self, local_path: str) -> PreparedWorkspace:
        normalized_path = normalize_local_path(local_path)
        identity_hash = Repository.build_identity_hash(RepositorySourceType.LOCAL, local_path=str(normalized_path))
        default_branch = extract_default_branch(normalized_path)
        commit_hash = extract_commit_hash(normalized_path)
        repository, _ = Repository.objects.update_or_create(
            identity_hash=identity_hash,
            defaults={
                "source_type": RepositorySourceType.LOCAL,
                "url": "",
                "name": normalized_path.name,
                "default_branch": default_branch,
                "local_path": str(normalized_path),
                "commit_hash": commit_hash,
                "indexed_at": timezone.now(),
            },
        )
        return PreparedWorkspace(
            repository=repository,
            workspace_path=normalized_path,
            commit_hash=commit_hash,
            default_branch=default_branch,
        )

    def _shallow_clone(self, repo_url: str, workspace_path: Path) -> None:
        workspace_path.parent.mkdir(parents=True, exist_ok=True)
        command = [
            "git",
            "clone",
            "--depth=1",
            "--single-branch",
            repo_url,
            str(workspace_path),
        ]
        subprocess.run(command, check=True, capture_output=True, text=True, timeout=120)

    @contextlib.contextmanager
    def _lock(self, identity_hash: str):
        lock_path = settings.REPO_CACHE_ROOT / f"{identity_hash}.lock"
        for _ in range(80):
            try:
                fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, str(time.time()).encode("utf-8"))
                os.close(fd)
                break
            except FileExistsError:
                time.sleep(0.25)
        else:
            raise TimeoutError("Timed out waiting for repository preparation lock.")

        try:
            yield
        finally:
            with contextlib.suppress(FileNotFoundError):
                lock_path.unlink()


class RepositorySessionLookupService:
    @staticmethod
    def list_sessions(repository_id: int):
        from apps.research.models import ResearchSession

        return ResearchSession.objects.filter(repository_id=repository_id).select_related("repository")


class RepositoryRegistrationService:
    def register(self, *, source_type: str, repo_url: str = "", local_path: str = "") -> Repository:
        if source_type == RepositorySourceType.GITHUB:
            owner, repo_name = validate_public_github_url(repo_url)
            identity_hash = Repository.build_identity_hash(RepositorySourceType.GITHUB, url=repo_url)
            cache_path = settings.REPO_CACHE_ROOT / identity_hash
            repository, _ = Repository.objects.update_or_create(
                identity_hash=identity_hash,
                defaults={
                    "source_type": RepositorySourceType.GITHUB,
                    "url": repo_url,
                    "name": repo_name,
                    "default_branch": "",
                    "local_path": str(cache_path),
                    "commit_hash": "",
                },
            )
            return repository

        normalized_path = normalize_local_path(local_path)
        identity_hash = Repository.build_identity_hash(RepositorySourceType.LOCAL, local_path=str(normalized_path))
        repository, _ = Repository.objects.update_or_create(
            identity_hash=identity_hash,
            defaults={
                "source_type": RepositorySourceType.LOCAL,
                "url": "",
                "name": normalized_path.name,
                "default_branch": "",
                "local_path": str(normalized_path),
                "commit_hash": "",
            },
        )
        return repository

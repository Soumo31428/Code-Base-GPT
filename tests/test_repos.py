from pathlib import Path

import pytest
from django.core.exceptions import ValidationError

from apps.repos.models import Repository, RepositorySourceType
from apps.repos.services import RepositoryRegistrationService, normalize_local_path, validate_public_github_url


@pytest.mark.django_db
def test_repository_requires_url_for_github():
    repository = Repository(source_type=RepositorySourceType.GITHUB, name="repo", local_path="/tmp/repo")
    with pytest.raises(ValidationError):
        repository.full_clean()


def test_validate_public_github_url_accepts_public_repo():
    owner, repo = validate_public_github_url("https://github.com/openai/openai-python")
    assert owner == "openai"
    assert repo == "openai-python"


@pytest.mark.django_db
def test_register_local_repository_normalizes_path(tmp_path, settings):
    settings.SAFE_LOCAL_REPO_ROOTS = [tmp_path.resolve()]
    repo_dir = tmp_path / "example"
    repo_dir.mkdir()

    repository = RepositoryRegistrationService().register(
        source_type=RepositorySourceType.LOCAL,
        local_path=str(repo_dir),
    )

    assert Path(repository.local_path) == repo_dir.resolve()
    assert repository.identity_hash == Repository.build_identity_hash("local", local_path=str(repo_dir.resolve()))


def test_normalize_local_path_rejects_unsafe_root(tmp_path, settings):
    settings.SAFE_LOCAL_REPO_ROOTS = [(tmp_path / "safe").resolve()]
    repo_dir = tmp_path / "outside"
    repo_dir.mkdir()

    with pytest.raises(ValidationError):
        normalize_local_path(str(repo_dir))

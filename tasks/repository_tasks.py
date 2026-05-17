from __future__ import annotations

from celery import shared_task
from django.utils import timezone

from apps.repos.models import Repository
from apps.repos.services import RepositoryPreparationService


@shared_task(name="prepare_repository_task")
def prepare_repository_task(repository_id: int) -> None:
    repository = Repository.objects.get(id=repository_id)
    prepared = RepositoryPreparationService().prepare(
        source_type=repository.source_type,
        repo_url=repository.url,
        local_path=repository.local_path,
    )
    repository.local_path = str(prepared.workspace_path)
    repository.default_branch = prepared.default_branch
    repository.commit_hash = prepared.commit_hash
    repository.indexed_at = timezone.now()
    repository.save(update_fields=["local_path", "default_branch", "commit_hash", "indexed_at", "updated_at"])


@shared_task(name="refresh_repository_metadata_task")
def refresh_repository_metadata_task(repository_id: int) -> None:
    prepare_repository_task(repository_id)

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.conf import settings
from django.utils import timezone

from apps.repos.models import Repository
from apps.repos.services import RepositoryRegistrationService
from .models import ResearchSession, SessionStatus


@dataclass(frozen=True)
class SessionCreateResult:
    repository: Repository
    session: ResearchSession


class ResearchSessionService:
    def create_session(self, *, source_type: str, question: str, repo_url: str = "", local_path: str = "") -> SessionCreateResult:
        repository = RepositoryRegistrationService().register(source_type=source_type, repo_url=repo_url, local_path=local_path)
        session = ResearchSession.objects.create(
            repository=repository,
            question=question,
            status=SessionStatus.PENDING,
            model_name=settings.OPENAI_MODEL,
        )

        from tasks.research_tasks import run_research_session_task

        run_research_session_task.delay(session.id)
        return SessionCreateResult(repository=repository, session=session)

    def mark_running(self, session: ResearchSession) -> None:
        session.status = SessionStatus.RUNNING
        session.save(update_fields=["status"])

    def mark_completed(self, session: ResearchSession, *, answer: str, total_tokens: int, duration_ms: int, iterations_used: int) -> None:
        session.status = SessionStatus.COMPLETED
        session.answer = answer
        session.total_tokens = total_tokens
        session.duration_ms = duration_ms
        session.iterations_used = iterations_used
        session.completed_at = timezone.now()
        session.save(
            update_fields=[
                "status",
                "answer",
                "total_tokens",
                "duration_ms",
                "iterations_used",
                "completed_at",
            ]
        )

    def mark_failed(self, session: ResearchSession, message: str) -> None:
        session.status = SessionStatus.FAILED
        session.answer = message
        session.completed_at = timezone.now()
        session.save(update_fields=["status", "answer", "completed_at"])

    def get_session(self, session_id: int) -> ResearchSession:
        return ResearchSession.objects.select_related("repository").prefetch_related("findings").get(id=session_id)

    def list_repository_sessions(self, repository_id: int):
        return ResearchSession.objects.filter(repository_id=repository_id).select_related("repository").prefetch_related("findings")

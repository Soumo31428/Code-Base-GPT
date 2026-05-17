from __future__ import annotations

import time
from pathlib import Path

from celery import shared_task

from agent.orchestrator import ResearchOrchestrator
from apps.research.models import ResearchSession, SummaryCache, SummaryScopeType
from apps.research.services import ResearchSessionService


@shared_task(name="run_research_session_task")
def run_research_session_task(session_id: int) -> None:
    service = ResearchSessionService()
    session = service.get_session(session_id)
    orchestrator = ResearchOrchestrator()
    started_at = time.perf_counter()
    service.mark_running(session)

    try:
        result = orchestrator.run(session)
        duration_ms = int((time.perf_counter() - started_at) * 1000)
        service.mark_completed(
            session,
            answer=result.answer,
            total_tokens=result.total_tokens,
            duration_ms=duration_ms,
            iterations_used=result.iterations_used,
        )
    except Exception as exc:
        service.mark_failed(session, f"Research failed: {exc}")
        raise


@shared_task(name="generate_summary_task")
def generate_summary_task(repository_id: int, path: str) -> None:
    from apps.repos.models import Repository

    repository = Repository.objects.get(id=repository_id)
    workspace = Path(repository.local_path).resolve()
    target = (workspace / path).resolve()
    if target != workspace and workspace not in target.parents:
        return
    if not target.exists() or not target.is_file():
        return
    lines = target.read_text(encoding="utf-8").splitlines()[:50]
    significant = [line.strip() for line in lines if line.strip()][:8]
    summary = f"{path} starts with: {' | '.join(significant)}" if significant else f"{path} is currently empty."
    SummaryCache.objects.update_or_create(
        repository=repository,
        scope_type=SummaryScopeType.FILE,
        scope_key=path,
        source_hash=repository.commit_hash or repository.identity_hash,
        defaults={
            "session": ResearchSession.objects.filter(repository=repository).order_by("-created_at").first(),
            "content": summary,
        },
    )

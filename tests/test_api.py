from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from agent.orchestrator import OrchestratorResult
from apps.repos.models import RepositorySourceType
from apps.research.models import ResearchSession, SessionStatus


@pytest.mark.django_db
def test_create_session_validates_local_path(tmp_path, settings):
    settings.SAFE_LOCAL_REPO_ROOTS = [tmp_path.resolve()]
    client = APIClient()

    response = client.post(
        "/api/v1/sessions/",
        {
            "source_type": RepositorySourceType.LOCAL,
            "question": "How does retry work?",
        },
        format="json",
    )

    assert response.status_code == 400
    assert "local_path" in response.json()


@pytest.mark.django_db
def test_create_session_enqueues_task(tmp_path, settings):
    settings.SAFE_LOCAL_REPO_ROOTS = [tmp_path.resolve()]
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    client = APIClient()

    with patch("tasks.research_tasks.run_research_session_task.delay") as delay_mock:
        response = client.post(
            "/api/v1/sessions/",
            {
                "source_type": RepositorySourceType.LOCAL,
                "local_path": str(repo_dir),
                "question": "How does retry work?",
            },
            format="json",
        )

    assert response.status_code == 202
    assert response.json()["status"] == SessionStatus.PENDING
    delay_mock.assert_called_once()


@pytest.mark.django_db
def test_run_research_session_task_marks_session_completed(tmp_path, settings):
    settings.SAFE_LOCAL_REPO_ROOTS = [tmp_path.resolve()]
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    (repo_dir / "worker.py").write_text("def retry():\n    return True\n", encoding="utf-8")
    client = APIClient()

    with patch("tasks.research_tasks.run_research_session_task.delay"):
        response = client.post(
            "/api/v1/sessions/",
            {
                "source_type": RepositorySourceType.LOCAL,
                "local_path": str(repo_dir),
                "question": "How does retry work?",
            },
            format="json",
        )

    session_id = response.json()["session_id"]

    with patch("tasks.research_tasks.ResearchOrchestrator.run", return_value=OrchestratorResult(answer="Grounded [worker.py:1-2]", total_tokens=9, iterations_used=2)):
        from tasks.research_tasks import run_research_session_task

        run_research_session_task(session_id)

    session = ResearchSession.objects.get(id=session_id)
    assert session.status == SessionStatus.COMPLETED
    assert session.total_tokens == 9


@pytest.mark.django_db
def test_repository_sessions_endpoint_returns_history(tmp_path, settings):
    settings.SAFE_LOCAL_REPO_ROOTS = [tmp_path.resolve()]
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    client = APIClient()

    with patch("tasks.research_tasks.run_research_session_task.delay"):
        response = client.post(
            "/api/v1/sessions/",
            {
                "source_type": RepositorySourceType.LOCAL,
                "local_path": str(repo_dir),
                "question": "How does retry work?",
            },
            format="json",
        )

    repo_id = response.json()["repository_id"]
    history_response = client.get(f"/api/v1/repos/{repo_id}/sessions/")

    assert history_response.status_code == 200
    assert len(history_response.json()) == 1

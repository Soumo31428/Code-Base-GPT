from pathlib import Path

import pytest

from agent.orchestrator import ResearchOrchestrator
from agent.synthesis.answer import AnswerSynthesizer
from agent.verification.grounding import AnswerVerifier
from apps.repos.models import Repository, RepositorySourceType
from apps.research.models import EvidenceType, Finding, ResearchSession


@pytest.mark.django_db
def test_verifier_accepts_grounded_answer(tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    (repo_dir / "worker.py").write_text("def retry():\n    return True\n", encoding="utf-8")

    repository = Repository.objects.create(
        source_type=RepositorySourceType.LOCAL,
        name="repo",
        local_path=str(repo_dir),
        url="",
    )
    session = ResearchSession.objects.create(repository=repository, question="How does retry work?")
    finding = Finding.objects.create(
        session=session,
        repository=repository,
        file_path="worker.py",
        line_start=1,
        line_end=2,
        note="Retry behavior lives in retry().",
        confidence=0.9,
        evidence_type=EvidenceType.DIRECT,
    )

    result = AnswerVerifier().verify(
        answer="Retry behavior is implemented in `retry` [worker.py:1-2].",
        findings=[finding],
        workspace_path=repo_dir,
        question=session.question,
    )

    assert result.is_valid is True
    assert result.gaps == []


@pytest.mark.django_db
def test_verifier_rejects_invalid_line_range(tmp_path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    (repo_dir / "worker.py").write_text("def retry():\n    return True\n", encoding="utf-8")

    result = AnswerVerifier().verify(
        answer="Retry behavior lives in [worker.py:1-20].",
        findings=[],
        workspace_path=repo_dir,
        question="How does retry work?",
    )

    assert result.is_valid is False
    assert any("Invalid citation range" in gap for gap in result.gaps)


@pytest.mark.django_db
def test_fallback_answer_ignores_gap_follow_up_notes():
    repository = Repository.objects.create(
        source_type=RepositorySourceType.LOCAL,
        name="repo",
        local_path="C:/repo",
        url="",
    )
    session = ResearchSession.objects.create(repository=repository, question="How does retry work?")
    direct = Finding.objects.create(
        session=session,
        repository=repository,
        file_path="worker.py",
        line_start=1,
        line_end=4,
        note="Query 'retry' matched symbol code in worker.py; representative line: def retry(self):",
        confidence=0.9,
        evidence_type=EvidenceType.DIRECT,
    )
    gap = Finding.objects.create(
        session=session,
        repository=repository,
        file_path="utils.py",
        line_start=10,
        line_end=12,
        note="Gap follow-up: Invalid citation range: docs.md:1-9",
        confidence=0.5,
        evidence_type=EvidenceType.CROSS_REFERENCE,
    )

    answer, _ = AnswerSynthesizer().synthesize(question=session.question, findings=[direct, gap])
    assert "Gap follow-up:" not in answer


@pytest.mark.django_db
def test_synthesis_findings_filter_prefers_core_direct_evidence():
    repository = Repository.objects.create(
        source_type=RepositorySourceType.LOCAL,
        name="fastapi",
        local_path="C:/repo",
        url="",
    )
    session = ResearchSession.objects.create(
        repository=repository,
        question="How does FastAPI handle dependency injection internally?",
    )
    core = Finding.objects.create(
        session=session,
        repository=repository,
        file_path="fastapi/dependencies/utils.py",
        line_start=598,
        line_end=684,
        note="Query 'solve_dependencies' matched symbol code in fastapi/dependencies/utils.py; representative line: async def solve_dependencies(",
        confidence=0.95,
        evidence_type=EvidenceType.DIRECT,
    )
    Finding.objects.create(
        session=session,
        repository=repository,
        file_path="docs_src/dependencies/tutorial001.py",
        line_start=1,
        line_end=10,
        note="Query 'Depends' matched symbol code in docs_src/dependencies/tutorial001.py; representative line: def common_parameters(",
        confidence=0.9,
        evidence_type=EvidenceType.DIRECT,
    )
    Finding.objects.create(
        session=session,
        repository=repository,
        file_path="fastapi/utils.py",
        line_start=10,
        line_end=12,
        note="Gap follow-up: Invalid citation range: fastapi/params.py:741-768",
        confidence=0.5,
        evidence_type=EvidenceType.CROSS_REFERENCE,
    )

    filtered = ResearchOrchestrator._get_synthesis_findings(session)

    assert filtered
    assert filtered[0].id == core.id
    assert all("docs_src/" not in finding.file_path for finding in filtered)
    assert all("Gap follow-up:" not in finding.note for finding in filtered)


def test_select_relevant_matches_prefers_dependency_symbols_in_core_files():
    matches = [
        {
            "file_path": "docs_src/dependencies/tutorial001.py",
            "line_number": 4,
            "snippet": "def solve_dependencies():",
            "relevance_hint": "symbol",
        },
        {
            "file_path": "fastapi/dependencies/utils.py",
            "line_number": 598,
            "snippet": "async def solve_dependencies(",
            "relevance_hint": "symbol",
        },
        {
            "file_path": "fastapi/routing.py",
            "line_number": 457,
            "snippet": "solved_result = await solve_dependencies(",
            "relevance_hint": "text",
        },
    ]

    ranked = ResearchOrchestrator._select_relevant_matches(matches, "solve_dependencies")

    assert ranked[0]["file_path"] == "fastapi/dependencies/utils.py"

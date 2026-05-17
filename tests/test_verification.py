from pathlib import Path

import pytest

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

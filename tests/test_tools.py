from pathlib import Path

import pytest

from agent.retrieval.lexical import LexicalSearchEngine
from agent.tools.base import ToolRuntimeState
from agent.tools.repository import RepositoryTools
from agent.types import WorkspaceContext
from apps.repos.models import Repository, RepositorySourceType
from apps.research.models import ResearchSession, SummaryCache


@pytest.mark.django_db
def test_search_sanitization():
    assert LexicalSearchEngine.sanitize_query("retry(); rm -rf /") == "retry rm -rf /"


@pytest.mark.django_db
def test_read_file_clamps_and_adds_continuation_hint(tmp_path, settings):
    settings.SAFE_LOCAL_REPO_ROOTS = [tmp_path.resolve()]
    settings.AGENT_READ_MAX_LINES = 150

    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    file_path = repo_dir / "sample.py"
    file_path.write_text("\n".join(f"line {index}" for index in range(1, 301)), encoding="utf-8")

    repository = Repository.objects.create(
        source_type=RepositorySourceType.LOCAL,
        name="repo",
        local_path=str(repo_dir),
        url="",
    )
    session = ResearchSession.objects.create(repository=repository, question="How does retry work?")
    tools = RepositoryTools(
        context=WorkspaceContext(
            session_id=session.id,
            repository_id=repository.id,
            workspace_path=repo_dir,
            commit_hash="",
        ),
        state=ToolRuntimeState(),
    )

    result = tools.read_file("sample.py", 10, 260)

    assert result["start_line"] == 10
    assert result["end_line"] == 159
    assert "after line 159" in result["continuation_hint"]


@pytest.mark.django_db
def test_search_code_finds_exact_identifier(tmp_path, settings):
    settings.SAFE_LOCAL_REPO_ROOTS = [tmp_path.resolve()]

    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    (repo_dir / "service.py").write_text(
        "def retry_policy():\n    return 'enabled'\n",
        encoding="utf-8",
    )

    repository = Repository.objects.create(
        source_type=RepositorySourceType.LOCAL,
        name="repo",
        local_path=str(repo_dir),
        url="",
    )
    session = ResearchSession.objects.create(repository=repository, question="retry policy")
    tools = RepositoryTools(
        context=WorkspaceContext(
            session_id=session.id,
            repository_id=repository.id,
            workspace_path=repo_dir,
            commit_hash="",
        ),
        state=ToolRuntimeState(),
    )

    matches = tools.search_code("retry_policy")

    assert matches
    assert matches[0]["file_path"] == "service.py"


@pytest.mark.django_db
def test_search_code_prefers_source_over_docs_and_tests(tmp_path, settings):
    settings.SAFE_LOCAL_REPO_ROOTS = [tmp_path.resolve()]

    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    (repo_dir / "README.md").write_text("dependency injection overview\n", encoding="utf-8")
    docs_dir = repo_dir / "docs"
    docs_dir.mkdir()
    (docs_dir / "guide.md").write_text("dependency injection docs\n", encoding="utf-8")
    tests_dir = repo_dir / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_dep.py").write_text("def test_dependency_injection():\n    pass\n", encoding="utf-8")
    pkg_dir = repo_dir / "fastapi"
    pkg_dir.mkdir()
    (pkg_dir / "utils.py").write_text("def solve_dependencies():\n    return 'dependency injection'\n", encoding="utf-8")

    repository = Repository.objects.create(
        source_type=RepositorySourceType.LOCAL,
        name="repo",
        local_path=str(repo_dir),
        url="",
    )
    session = ResearchSession.objects.create(repository=repository, question="dependency injection")
    tools = RepositoryTools(
        context=WorkspaceContext(
            session_id=session.id,
            repository_id=repository.id,
            workspace_path=repo_dir,
            commit_hash="",
        ),
        state=ToolRuntimeState(),
    )

    matches = tools.search_code("dependency injection")

    assert matches
    assert matches[0]["file_path"] == "fastapi/utils.py"


@pytest.mark.django_db
def test_duplicate_tool_call_fingerprint_counts_repeated_searches(tmp_path, settings):
    settings.SAFE_LOCAL_REPO_ROOTS = [tmp_path.resolve()]
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    (repo_dir / "service.py").write_text("def retry_policy():\n    return 'enabled'\n", encoding="utf-8")

    repository = Repository.objects.create(
        source_type=RepositorySourceType.LOCAL,
        name="repo",
        local_path=str(repo_dir),
        url="",
    )
    session = ResearchSession.objects.create(repository=repository, question="retry policy")
    state = ToolRuntimeState()
    tools = RepositoryTools(
        context=WorkspaceContext(
            session_id=session.id,
            repository_id=repository.id,
            workspace_path=repo_dir,
            commit_hash="",
        ),
        state=state,
    )

    tools.search_code("retry_policy")
    tools.search_code("retry_policy")

    assert state.tool_calls_used == 2
    assert any(count == 2 for count in state.fingerprints.values())


@pytest.mark.django_db
def test_file_summary_cache_invalidates_when_file_changes(tmp_path, settings):
    settings.SAFE_LOCAL_REPO_ROOTS = [tmp_path.resolve()]
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    target = repo_dir / "service.py"
    target.write_text("def retry_policy():\n    return 'enabled'\n", encoding="utf-8")

    repository = Repository.objects.create(
        source_type=RepositorySourceType.LOCAL,
        name="repo",
        local_path=str(repo_dir),
        url="",
    )
    session = ResearchSession.objects.create(repository=repository, question="retry policy")
    tools = RepositoryTools(
        context=WorkspaceContext(
            session_id=session.id,
            repository_id=repository.id,
            workspace_path=repo_dir,
            commit_hash="",
        ),
        state=ToolRuntimeState(),
    )

    first = tools.get_file_summary("service.py")
    target.write_text("def retry_policy():\n    return 'disabled'\n", encoding="utf-8")
    second = tools.get_file_summary("service.py")

    assert first["summary"] != second["summary"]
    assert SummaryCache.objects.filter(repository=repository, scope_key="service.py").count() == 2

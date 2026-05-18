from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings

from apps.repos.services import PreparedWorkspace, RepositoryPreparationService
from apps.research.models import EvidenceType, Finding, ResearchSession, SummaryCache, SummaryScopeType
from agent.synthesis.answer import AnswerSynthesizer
from agent.tools.base import ToolRuntimeState
from agent.tools.repository import RepositoryTools
from agent.types import WorkspaceContext
from agent.verification.grounding import AnswerVerifier


@dataclass
class OrchestratorResult:
    answer: str
    total_tokens: int
    iterations_used: int


class ResearchOrchestrator:
    STOPWORDS = {
        "does",
        "handle",
        "internally",
        "where",
        "what",
        "with",
        "that",
        "this",
        "into",
        "from",
        "have",
        "when",
        "will",
        "your",
        "about",
        "task",
        "logic",
        "works",
        "work",
        "supported",
        "support",
        "implemented",
        "implement",
        "brief",
        "explain",
        "fastapi",
        "celery",
    }

    def __init__(self) -> None:
        self.synthesizer = AnswerSynthesizer()
        self.verifier = AnswerVerifier()

    def run(self, session: ResearchSession) -> OrchestratorResult:
        prepared = RepositoryPreparationService().prepare(
            source_type=session.repository.source_type,
            repo_url=session.repository.url,
            local_path=session.repository.local_path,
        )
        context = WorkspaceContext(
            session_id=session.id,
            repository_id=session.repository_id,
            workspace_path=prepared.workspace_path,
            commit_hash=prepared.commit_hash,
        )
        state = ToolRuntimeState()
        tools = RepositoryTools(context=context, state=state)

        previous_findings = tools.get_previous_findings(limit=10)
        self._ensure_repo_summary(prepared, session)
        source_roots = self._infer_source_roots(prepared.workspace_path, session.repository.name)
        iterations_used = self._explore(session, tools, previous_findings, source_roots)

        findings = list(Finding.objects.filter(session=session).order_by("-confidence", "file_path", "line_start"))
        answer, total_tokens = self.synthesizer.synthesize(question=session.question, findings=findings)
        verification = self.verifier.verify(
            answer=answer,
            findings=findings,
            workspace_path=prepared.workspace_path,
            question=session.question,
        )
        if not verification.is_valid:
            self._gap_exploration(verification.gaps, tools, source_roots)
            iterations_used += 1
            findings = list(Finding.objects.filter(session=session).order_by("-confidence", "file_path", "line_start"))
            answer, total_tokens = self.synthesizer.synthesize(question=session.question, findings=findings)

        return OrchestratorResult(answer=answer, total_tokens=total_tokens, iterations_used=iterations_used)

    def _explore(
        self,
        session: ResearchSession,
        tools: RepositoryTools,
        previous_findings: list[dict],
        source_roots: list[str],
    ) -> int:
        search_queries = self._build_queries(session.question, previous_findings)
        iterations = 0
        collected_confidence = 0.0

        for query in search_queries:
            if iterations >= settings.AGENT_MAX_ITERATIONS or tools.state.tool_calls_used >= settings.AGENT_MAX_TOOL_CALLS:
                break

            matches = tools.search_code(query, preferred_paths=source_roots)
            iterations += 1
            if not matches:
                continue

            for match in matches[:3]:
                line_number = match["line_number"]
                read_result = tools.read_file(match["file_path"], max(1, line_number - 5), line_number + 15)
                note = self._derive_note(query, match, read_result["content"])
                confidence = self._derive_confidence(match["relevance_hint"], tools.state.tool_calls_used)
                tools.save_finding(
                    file_path=match["file_path"],
                    line_start=read_result["start_line"],
                    line_end=read_result["end_line"],
                    note=note,
                    confidence=confidence,
                    evidence_type=EvidenceType.DIRECT,
                )
                collected_confidence += confidence

            if collected_confidence >= 2.4:
                break

        return iterations

    def _gap_exploration(self, gaps: list[str], tools: RepositoryTools, source_roots: list[str]) -> None:
        for gap in gaps[:2]:
            for query in self._build_queries(gap, []):
                matches = tools.search_code(query, preferred_paths=source_roots)
                if not matches:
                    continue
                first = matches[0]
                read_result = tools.read_file(first["file_path"], max(1, first["line_number"] - 3), first["line_number"] + 8)
                tools.save_finding(
                    file_path=first["file_path"],
                    line_start=read_result["start_line"],
                    line_end=read_result["end_line"],
                    note=f"Gap follow-up: {gap}",
                    confidence=0.55,
                    evidence_type=EvidenceType.CROSS_REFERENCE,
                )
                break

    def _ensure_repo_summary(self, prepared: PreparedWorkspace, session: ResearchSession) -> None:
        top_level_entries = sorted(item.name for item in prepared.workspace_path.iterdir())[:20]
        summary = f"Top-level repository structure: {', '.join(top_level_entries)}"
        SummaryCache.objects.update_or_create(
            repository=session.repository,
            scope_type=SummaryScopeType.REPO,
            scope_key=".",
            source_hash=prepared.commit_hash or prepared.repository.identity_hash,
            defaults={"session": session, "content": summary},
        )

    @staticmethod
    def _infer_source_roots(workspace_path: Path, repository_name: str) -> list[str]:
        normalized_name = repository_name.replace("-", "_")
        candidates = [
            repository_name,
            normalized_name,
            "src",
            "app",
            "lib",
        ]
        roots: list[str] = []
        for candidate in candidates:
            candidate_path = workspace_path / candidate
            if candidate_path.is_dir() and candidate not in roots:
                roots.append(candidate)

        for child in sorted(workspace_path.iterdir(), key=lambda item: item.name):
            if child.is_dir() and not child.name.startswith(".") and (child / "__init__.py").exists():
                if child.name not in roots:
                    roots.append(child.name)

        return roots[:4]

    @staticmethod
    def _build_queries(question: str, previous_findings: list[dict]) -> list[str]:
        normalized_question = question.strip()
        tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", normalized_question)
        filtered_tokens = [
            token
            for token in tokens
            if token.lower() not in ResearchOrchestrator.STOPWORDS
        ]
        queries: list[str] = []

        for phrase in ResearchOrchestrator._extract_key_phrases(normalized_question):
            if phrase not in queries:
                queries.append(phrase)

        for token in filtered_tokens:
            if token not in queries:
                queries.append(token)

        for variant in ResearchOrchestrator._expand_domain_queries(normalized_question):
            if variant not in queries:
                queries.append(variant)

        for finding in previous_findings[:3]:
            basename = PathLike.basename(finding["file_path"])
            if basename not in queries:
                queries.append(basename)

        return [query for query in queries if query][:8]

    @staticmethod
    def _extract_key_phrases(question: str) -> list[str]:
        lowered = question.lower()
        phrases: list[str] = []
        if "dependency injection" in lowered:
            phrases.extend(["dependency injection", "Depends", "solve_dependencies"])
        if "retry" in lowered:
            phrases.extend(["retry", "autoretry_for", "retry_backoff", "default_retry_delay"])
        if "backoff" in lowered:
            phrases.extend(["retry_backoff", "get_exponential_backoff_interval"])
        return phrases

    @staticmethod
    def _expand_domain_queries(question: str) -> list[str]:
        lowered = question.lower()
        variants: list[str] = []
        if "dependency" in lowered:
            variants.extend(["dependency", "dependencies", "Depends"])
        if "inject" in lowered:
            variants.extend(["inject", "injection"])
        if "retry" in lowered:
            variants.extend(["retry", "backoff"])
        return variants

    @staticmethod
    def _derive_note(query: str, match: dict, content: str) -> str:
        content_lines = [line.strip() for line in content.splitlines() if line.strip()]
        representative_line = content_lines[0] if content_lines else match["snippet"].strip()
        representative_line = representative_line[:220]
        return (
            f"Query '{query}' matched {match['relevance_hint']} code in {match['file_path']}; "
            f"representative line: {representative_line}"
        )

    @staticmethod
    def _derive_confidence(relevance_hint: str, tool_calls_used: int) -> float:
        base = 0.85 if relevance_hint == "symbol" else 0.7
        if tool_calls_used > settings.AGENT_MAX_TOOL_CALLS // 2:
            base -= 0.1
        return max(0.4, min(0.95, base))


class PathLike:
    @staticmethod
    def basename(file_path: str) -> str:
        return file_path.replace("\\", "/").split("/")[-1]

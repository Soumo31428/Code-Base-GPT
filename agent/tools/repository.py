from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Sequence

from django.conf import settings

from apps.research.models import Finding, ResearchSession, SummaryCache, SummaryScopeType
from agent.retrieval.lexical import LexicalSearchEngine
from agent.tools.base import ToolExecutor, ToolRuntimeState
from agent.types import FileReadResult, ToolExecutionResult, WorkspaceContext


class RepositoryTools:
    def __init__(self, context: WorkspaceContext, state: ToolRuntimeState | None = None):
        self.context = context
        self.state = state or ToolRuntimeState()
        self.executor = ToolExecutor(context, self.state)
        self.search_engine = LexicalSearchEngine(context.workspace_path)

    def list_files(self, path: str = ".") -> list[str]:
        def callback() -> ToolExecutionResult:
            base_path = self.executor.ensure_within_workspace(path)
            entries = sorted(
                str(item.relative_to(self.context.workspace_path))
                for item in base_path.iterdir()
                if not item.name.startswith(".git")
            )[:200]
            return ToolExecutionResult(entries, f"listed {len(entries)} entries in {path}")

        return self.executor.execute("list_files", {"path": path}, callback)

    def search_code(self, query: str, preferred_paths: Sequence[str] | None = None) -> list[dict]:
        def callback() -> ToolExecutionResult:
            matches = self.search_engine.search(query, preferred_paths=preferred_paths)
            payload = [
                {
                    "file_path": match.file_path,
                    "line_number": match.line_number,
                    "snippet": match.snippet,
                    "relevance_hint": match.relevance_hint,
                }
                for match in matches
            ]
            return ToolExecutionResult(payload, f"found {len(payload)} lexical matches")

        return self.executor.execute(
            "search_code",
            {"query": query, "preferred_paths": list(preferred_paths or [])},
            callback,
        )

    def read_file(self, path: str, start_line: int, end_line: int) -> dict:
        def callback() -> ToolExecutionResult:
            file_path = self.executor.ensure_within_workspace(path)
            clamped_start = max(1, start_line)
            max_lines = settings.AGENT_READ_MAX_LINES
            clamped_end = min(max(clamped_start, end_line), clamped_start + max_lines - 1)
            lines = file_path.read_text(encoding="utf-8").splitlines()
            content = "\n".join(lines[clamped_start - 1 : clamped_end])
            result = FileReadResult(
                file_path=path,
                start_line=clamped_start,
                end_line=clamped_end,
                content=content,
                has_more_before=clamped_start > 1,
                has_more_after=clamped_end < len(lines),
            )
            payload = {
                "file_path": result.file_path,
                "start_line": result.start_line,
                "end_line": result.end_line,
                "content": result.content,
                "continuation_hint": self._build_continuation_hint(result),
            }
            return ToolExecutionResult(payload, f"read {path}:{clamped_start}-{clamped_end}")

        return self.executor.execute(
            "read_file",
            {"path": path, "start_line": start_line, "end_line": end_line},
            callback,
        )

    def get_file_summary(self, path: str) -> dict:
        def callback() -> ToolExecutionResult:
            file_path = self.executor.ensure_within_workspace(path)
            source_hash = self._hash_file(file_path)
            cached = SummaryCache.objects.filter(
                repository_id=self.context.repository_id,
                scope_type=SummaryScopeType.FILE,
                scope_key=path,
                source_hash=source_hash,
            ).first()
            if cached:
                payload = {"path": path, "summary": cached.content, "cached": True}
                return ToolExecutionResult(payload, f"loaded cached summary for {path}")

            lines = file_path.read_text(encoding="utf-8").splitlines()[:50]
            summary = self._summarize_lines(path, lines)
            SummaryCache.objects.update_or_create(
                repository_id=self.context.repository_id,
                scope_type=SummaryScopeType.FILE,
                scope_key=path,
                source_hash=source_hash,
                defaults={"session_id": self.context.session_id, "content": summary},
            )
            payload = {"path": path, "summary": summary, "cached": False}
            return ToolExecutionResult(payload, f"generated summary for {path}")

        return self.executor.execute("get_file_summary", {"path": path}, callback)

    def save_finding(
        self,
        *,
        file_path: str,
        line_start: int,
        line_end: int,
        note: str,
        confidence: float,
        evidence_type: str,
    ) -> dict:
        def callback() -> ToolExecutionResult:
            finding = Finding.objects.create(
                session_id=self.context.session_id,
                repository_id=self.context.repository_id,
                file_path=file_path,
                line_start=line_start,
                line_end=line_end,
                note=note,
                confidence=confidence,
                evidence_type=evidence_type,
            )
            payload = {"id": finding.id, "file_path": file_path, "note": note}
            return ToolExecutionResult(payload, f"saved finding for {file_path}:{line_start}-{line_end}")

        return self.executor.execute(
            "save_finding",
            {
                "file_path": file_path,
                "line_start": line_start,
                "line_end": line_end,
                "confidence": confidence,
                "evidence_type": evidence_type,
            },
            callback,
        )

    def get_previous_findings(self, limit: int = 20) -> list[dict]:
        def callback() -> ToolExecutionResult:
            findings = Finding.objects.filter(repository_id=self.context.repository_id).exclude(session_id=self.context.session_id)[:limit]
            payload = [
                {
                    "file_path": finding.file_path,
                    "line_start": finding.line_start,
                    "line_end": finding.line_end,
                    "note": finding.note,
                    "confidence": finding.confidence,
                    "evidence_type": finding.evidence_type,
                }
                for finding in findings
            ]
            return ToolExecutionResult(payload, f"loaded {len(payload)} previous findings")

        return self.executor.execute("get_previous_findings", {"limit": limit}, callback)

    def list_past_sessions(self, limit: int = 10) -> list[dict]:
        def callback() -> ToolExecutionResult:
            sessions = ResearchSession.objects.filter(repository_id=self.context.repository_id).exclude(id=self.context.session_id)[:limit]
            payload = [
                {
                    "id": session.id,
                    "question": session.question,
                    "status": session.status,
                    "created_at": session.created_at.isoformat(),
                }
                for session in sessions
            ]
            return ToolExecutionResult(payload, f"loaded {len(payload)} past sessions")

        return self.executor.execute("list_past_sessions", {"limit": limit}, callback)

    @staticmethod
    def _build_continuation_hint(result: FileReadResult) -> str:
        if result.has_more_before and result.has_more_after:
            return f"More context exists before line {result.start_line} and after line {result.end_line}."
        if result.has_more_before:
            return f"More context exists before line {result.start_line}."
        if result.has_more_after:
            return f"More context exists after line {result.end_line}."
        return "No additional nearby context."

    @staticmethod
    def _summarize_lines(path: str, lines: list[str]) -> str:
        significant = [line.strip() for line in lines if line.strip()][:8]
        if not significant:
            return f"{path} is currently empty."
        return f"{path} starts with: " + " | ".join(significant)

    @staticmethod
    def summarize_content_snippet(content: str) -> str:
        significant = [line.strip() for line in content.splitlines() if line.strip()]
        if not significant:
            return "No non-empty code lines in the selected range."
        return significant[0][:240]

    @staticmethod
    def _hash_file(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

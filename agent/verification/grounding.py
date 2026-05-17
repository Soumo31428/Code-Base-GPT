from __future__ import annotations

import re
from pathlib import Path

from apps.research.models import Finding
from agent.types import VerificationResult


CITATION_RE = re.compile(r"\[([^\]:]+):(\d+)-(\d+)\]")


class AnswerVerifier:
    def verify(self, *, answer: str, findings: list[Finding], workspace_path: Path, question: str) -> VerificationResult:
        gaps: list[str] = []
        citations = CITATION_RE.findall(answer)
        if not citations:
            gaps.append("The answer does not contain any citations.")

        finding_index = {(finding.file_path, finding.line_start, finding.line_end) for finding in findings}

        for file_path, start_raw, end_raw in citations:
            start_line = int(start_raw)
            end_line = int(end_raw)
            full_path = (workspace_path / file_path).resolve()
            if not full_path.exists():
                gaps.append(f"Cited path does not exist: {file_path}")
                continue
            line_count = len(full_path.read_text(encoding="utf-8").splitlines())
            if start_line < 1 or end_line < start_line or end_line > line_count:
                gaps.append(f"Invalid citation range: {file_path}:{start_line}-{end_line}")
            if (file_path, start_line, end_line) not in finding_index:
                gaps.append(f"Citation is not backed by a recorded finding: {file_path}:{start_line}-{end_line}")

        question_terms = {term.lower() for term in re.findall(r"[A-Za-z_]{4,}", question)}
        if question_terms and not any(term in answer.lower() for term in list(question_terms)[:3]):
            gaps.append("The answer may not fully address the question wording.")

        return VerificationResult(is_valid=not gaps, gaps=gaps)

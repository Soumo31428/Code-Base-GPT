from __future__ import annotations

import asyncio
from typing import Iterable

from django.conf import settings
from openai import AsyncOpenAI

from apps.research.models import Finding


class AnswerSynthesizer:
    def __init__(self) -> None:
        self.client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY) if settings.OPENAI_API_KEY else None

    def synthesize(self, *, question: str, findings: Iterable[Finding]) -> tuple[str, int]:
        findings_list = list(findings)
        if self.client:
            return asyncio.run(self._synthesize_with_llm(question, findings_list))
        return self._fallback_answer(question, findings_list), 0

    async def _synthesize_with_llm(self, question: str, findings: list[Finding]) -> tuple[str, int]:
        evidence = "\n".join(
            f"- {finding.note} [{finding.file_path}:{finding.line_start}-{finding.line_end}] ({finding.evidence_type})"
            for finding in findings[:20]
        )
        response = await self.client.responses.create(
            model=settings.OPENAI_MODEL,
            # reasoning={"effort": "minimal"},
            # text={"verbosity": "low"},
            max_output_tokens=300,
            input=[
                {
                    "role": "system",
                    "content": (
                        "Answer repository questions using only the supplied findings. "
                        "Every substantive claim must cite [path:start-end]. Mark inferred claims clearly."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Question: {question}\n\nFindings:\n{evidence}",
                },
            ],
        )
        text = response.output_text.strip()
        tokens = getattr(response, "usage", None)
        total_tokens = getattr(tokens, "total_tokens", 0) if tokens else 0
        return text, total_tokens

    def _fallback_answer(self, question: str, findings: list[Finding]) -> str:
        if not findings:
            return (
                f"I could not find grounded evidence to answer: {question}\n\n"
                "No findings were collected, so the answer is intentionally incomplete."
            )
        direct_findings = [finding for finding in findings if finding.evidence_type == "direct"]
        preferred = direct_findings[:5] or findings[:5]
        bullet_lines = [
            f"- {finding.note} [{finding.file_path}:{finding.line_start}-{finding.line_end}]"
            for finding in preferred
            if "Gap follow-up:" not in finding.note
        ]
        if not bullet_lines:
            bullet_lines = [
                f"- {finding.note} [{finding.file_path}:{finding.line_start}-{finding.line_end}]"
                for finding in preferred
            ]
        return (
            f"Grounded answer for: {question}\n"
            "Most relevant implementation evidence:\n"
            + "\n".join(bullet_lines)
        )

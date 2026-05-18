from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Sequence

from django.conf import settings

from agent.types import SearchMatch


SAFE_QUERY_RE = re.compile(r"[^A-Za-z0-9_\-./:@ ]+")
SKIP_GLOBS = [
    "!.git",
    "!node_modules",
    "!dist",
    "!build",
    "!.venv",
    "!venv",
    "!__pycache__",
]
SOURCE_ONLY_GLOBS = [
    "*.py",
    "*.pyi",
    "*.js",
    "*.ts",
    "*.tsx",
    "*.go",
    "*.rs",
    "*.java",
]
SOURCE_EXCLUDE_GLOBS = [
    "!docs/**",
    "!doc/**",
    "!documentation/**",
    "!docs_src/**",
    "!tests/**",
    "!test/**",
    "!benchmarks/**",
    "!README*",
]


class LexicalSearchEngine:
    def __init__(self, workspace_path: Path):
        self.workspace_path = workspace_path

    @staticmethod
    def sanitize_query(query: str) -> str:
        sanitized = SAFE_QUERY_RE.sub(" ", query).strip()
        return re.sub(r"\s+", " ", sanitized)

    def search(self, query: str, preferred_paths: Sequence[str] | None = None) -> list[SearchMatch]:
        sanitized = self.sanitize_query(query)
        if not sanitized:
            return []

        targets = [target for target in (preferred_paths or []) if target] or ["."]
        if targets != ["."]:
            preferred_matches = self._run_rg(
                sanitized,
                include_globs=SOURCE_ONLY_GLOBS,
                exclude_globs=SKIP_GLOBS + SOURCE_EXCLUDE_GLOBS,
                targets=targets,
                timeout=settings.AGENT_TOOL_TIMEOUT_SECONDS,
            )
            if preferred_matches:
                return preferred_matches

        source_first_matches = self._run_rg(
            sanitized,
            include_globs=SOURCE_ONLY_GLOBS,
            exclude_globs=SKIP_GLOBS + SOURCE_EXCLUDE_GLOBS,
            targets=["."],
            timeout=settings.AGENT_TOOL_TIMEOUT_SECONDS,
        )
        if source_first_matches:
            return source_first_matches

        return self._run_rg(
            sanitized,
            include_globs=[],
            exclude_globs=SKIP_GLOBS,
            targets=targets,
            timeout=max(3, settings.AGENT_TOOL_TIMEOUT_SECONDS // 2),
        )

    def _run_rg(
        self,
        query: str,
        *,
        include_globs: list[str],
        exclude_globs: list[str],
        targets: Sequence[str],
        timeout: int,
    ) -> list[SearchMatch]:
        command = [
            "rg",
            "--line-number",
            "--context",
            "2",
            "--smart-case",
            "--no-messages",
            "--fixed-strings",
            "--max-filesize",
            "1M",
            "--max-count",
            str(settings.AGENT_SEARCH_MAX_RESULTS),
        ]
        for glob in include_globs:
            command.extend(["--glob", glob])
        for glob in exclude_globs:
            command.extend(["--glob", glob])
        command.append(query)
        command.extend(targets)
        try:
            completed = subprocess.run(
                command,
                cwd=self.workspace_path,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return []
        if completed.returncode not in (0, 1):
            raise RuntimeError(completed.stderr.strip() or "rg search failed")
        return self._parse_output(completed.stdout)

    def _parse_output(self, output: str) -> list[SearchMatch]:
        matches: list[SearchMatch] = []
        for line in output.splitlines():
            if not line or line.startswith("--"):
                continue
            parts = line.split(":", 2)
            if len(parts) != 3 or not parts[1].isdigit():
                continue
            file_path, line_number, snippet = parts
            normalized_path = self._normalize_path(file_path)
            matches.append(
                SearchMatch(
                    file_path=normalized_path,
                    line_number=int(line_number),
                    snippet=snippet.strip(),
                    relevance_hint=self._infer_relevance(snippet),
                )
            )
        ranked = sorted(matches, key=self._rank_match, reverse=True)
        return ranked[: settings.AGENT_SEARCH_MAX_RESULTS]

    @staticmethod
    def _infer_relevance(snippet: str) -> str:
        lowered = snippet.lower()
        if "def " in lowered or "class " in lowered:
            return "symbol"
        if "import " in lowered or "from " in lowered:
            return "import"
        if "@" in snippet:
            return "decorator"
        return "text"

    @staticmethod
    def _normalize_path(file_path: str) -> str:
        normalized = file_path.replace("\\", "/")
        if normalized.startswith("./"):
            return normalized[2:]
        if normalized.startswith(".\\"):
            return normalized[2:]
        return normalized

    @classmethod
    def _rank_match(cls, match: SearchMatch) -> tuple[int, int, int]:
        path = match.file_path.lower()
        extension = Path(path).suffix.lower()

        source_score = 0
        if extension in {".py", ".pyi"}:
            source_score += 5
        elif extension in {".js", ".ts", ".tsx", ".go", ".rs", ".java"}:
            source_score += 3
        elif extension in {".md", ".rst"}:
            source_score -= 6

        if any(marker in path for marker in ("docs/", "doc/", "documentation/")):
            source_score -= 8
        if any(marker in path for marker in ("tests/", "test_", "/test/", "benchmarks/")):
            source_score -= 5
        if path.endswith("readme.md") or "/readme." in path:
            source_score -= 9
        if any(marker in path for marker in ("site-packages/", ".venv/", "venv/")):
            source_score -= 10
        if any(marker in path for marker in ("dependencies/", "routing/", "params", "utils")):
            source_score += 2

        relevance_score = {
            "symbol": 4,
            "import": 2,
            "decorator": 2,
            "text": 0,
        }.get(match.relevance_hint, 0)

        line_bias = max(0, 100000 - match.line_number)
        return (source_score, relevance_score, line_bias)

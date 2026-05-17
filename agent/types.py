from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class SearchMatch:
    file_path: str
    line_number: int
    snippet: str
    relevance_hint: str


@dataclass
class FileReadResult:
    file_path: str
    start_line: int
    end_line: int
    content: str
    has_more_before: bool
    has_more_after: bool


@dataclass
class VerificationResult:
    is_valid: bool
    gaps: list[str] = field(default_factory=list)


@dataclass
class ToolExecutionResult:
    data: object
    summary: str


@dataclass
class WorkspaceContext:
    session_id: int
    repository_id: int
    workspace_path: Path
    commit_hash: str

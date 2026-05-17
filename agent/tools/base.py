from __future__ import annotations

import hashlib
import json
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from apps.research.models import ToolCallLog
from agent.types import ToolExecutionResult, WorkspaceContext


@dataclass
class ToolRuntimeState:
    fingerprints: Counter[str] = field(default_factory=Counter)
    tool_calls_used: int = 0

    def register(self, tool_name: str, arguments: dict) -> int:
        payload = json.dumps({"tool": tool_name, "arguments": arguments}, sort_keys=True)
        fingerprint = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        self.fingerprints[fingerprint] += 1
        self.tool_calls_used += 1
        return self.fingerprints[fingerprint]


class ToolExecutor:
    def __init__(self, context: WorkspaceContext, state: ToolRuntimeState):
        self.context = context
        self.state = state

    def execute(self, tool_name: str, arguments: dict, callback: Callable[[], ToolExecutionResult]) -> object:
        duplicate_count = self.state.register(tool_name, arguments)
        started_at = time.perf_counter()
        try:
            result = callback()
            summary = result.summary
            data = result.data
        except Exception as exc:
            summary = f"failed: {exc}"
            data = None
            raise
        finally:
            duration_ms = int((time.perf_counter() - started_at) * 1000)
            ToolCallLog.objects.create(
                session_id=self.context.session_id,
                tool_name=tool_name,
                arguments_json={**arguments, "duplicate_count": duplicate_count},
                result_summary=summary if len(summary) < 1000 else summary[:997] + "...",
                duration_ms=duration_ms,
            )
        return data

    def ensure_within_workspace(self, relative_path: str) -> Path:
        candidate = (self.context.workspace_path / relative_path).resolve()
        if candidate != self.context.workspace_path and self.context.workspace_path not in candidate.parents:
            raise ValueError("Path escapes the repository workspace.")
        return candidate

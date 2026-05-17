from __future__ import annotations

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.repos.models import Repository


class SessionStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    RUNNING = "running", "Running"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"


class EvidenceType(models.TextChoices):
    DIRECT = "direct", "Direct"
    INFERRED = "inferred", "Inferred"
    CROSS_REFERENCE = "cross_reference", "Cross reference"


class SummaryScopeType(models.TextChoices):
    REPO = "repo", "Repository"
    DIRECTORY = "directory", "Directory"
    FILE = "file", "File"


class ResearchSession(models.Model):
    repository = models.ForeignKey(Repository, on_delete=models.CASCADE, related_name="sessions")
    question = models.TextField()
    answer = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=SessionStatus.choices, default=SessionStatus.PENDING)
    model_name = models.CharField(max_length=255, blank=True)
    total_tokens = models.PositiveIntegerField(default=0)
    duration_ms = models.PositiveIntegerField(default=0)
    iterations_used = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Session {self.pk} - {self.status}"


class Finding(models.Model):
    session = models.ForeignKey(ResearchSession, on_delete=models.CASCADE, related_name="findings")
    repository = models.ForeignKey(Repository, on_delete=models.CASCADE, related_name="findings")
    file_path = models.CharField(max_length=1024)
    line_start = models.PositiveIntegerField()
    line_end = models.PositiveIntegerField()
    note = models.TextField()
    confidence = models.FloatField(validators=[MinValueValidator(0.0), MaxValueValidator(1.0)])
    evidence_type = models.CharField(max_length=32, choices=EvidenceType.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["file_path", "line_start", "created_at"]


class ToolCallLog(models.Model):
    session = models.ForeignKey(ResearchSession, on_delete=models.CASCADE, related_name="tool_logs")
    tool_name = models.CharField(max_length=255)
    arguments_json = models.JSONField(default=dict)
    result_summary = models.TextField()
    duration_ms = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]


class SummaryCache(models.Model):
    repository = models.ForeignKey(Repository, on_delete=models.CASCADE, related_name="summaries")
    session = models.ForeignKey(
        ResearchSession,
        on_delete=models.SET_NULL,
        related_name="summary_cache_entries",
        null=True,
        blank=True,
    )
    scope_type = models.CharField(max_length=20, choices=SummaryScopeType.choices)
    scope_key = models.CharField(max_length=1024)
    content = models.TextField()
    source_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("repository", "scope_type", "scope_key", "source_hash")
        ordering = ["scope_type", "scope_key"]


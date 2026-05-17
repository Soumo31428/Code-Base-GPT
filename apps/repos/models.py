from __future__ import annotations

import hashlib
from pathlib import Path

from django.core.exceptions import ValidationError
from django.db import models


class RepositorySourceType(models.TextChoices):
    GITHUB = "github", "GitHub"
    LOCAL = "local", "Local"


class Repository(models.Model):
    source_type = models.CharField(max_length=20, choices=RepositorySourceType.choices)
    url = models.URLField(blank=True)
    name = models.CharField(max_length=255)
    default_branch = models.CharField(max_length=255, blank=True)
    local_path = models.CharField(max_length=1024)
    commit_hash = models.CharField(max_length=64, blank=True)
    identity_hash = models.CharField(max_length=64, unique=True, editable=False)
    indexed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def clean(self) -> None:
        if self.source_type == RepositorySourceType.GITHUB and not self.url:
            raise ValidationError({"url": "GitHub repositories require a URL."})
        if self.source_type == RepositorySourceType.LOCAL and not self.local_path:
            raise ValidationError({"local_path": "Local repositories require a local path."})

    def save(self, *args, **kwargs):  # type: ignore[override]
        self.identity_hash = self.build_identity_hash(self.source_type, self.url, self.local_path)
        if not self.name:
            if self.url:
                self.name = self.url.rstrip("/").split("/")[-1]
            else:
                self.name = Path(self.local_path).name
        self.full_clean()
        return super().save(*args, **kwargs)

    @staticmethod
    def build_identity_hash(source_type: str, url: str = "", local_path: str = "") -> str:
        if source_type == RepositorySourceType.GITHUB:
            value = url.strip().lower().rstrip("/")
        else:
            value = str(Path(local_path).resolve()).lower()
        payload = f"{source_type}:{value}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def __str__(self) -> str:
        return f"{self.name} ({self.source_type})"


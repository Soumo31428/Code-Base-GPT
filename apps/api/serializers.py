from __future__ import annotations

from rest_framework import serializers

from apps.repos.models import Repository, RepositorySourceType
from apps.research.models import Finding, ResearchSession


class SessionCreateSerializer(serializers.Serializer):
    source_type = serializers.ChoiceField(choices=RepositorySourceType.choices)
    repo_url = serializers.URLField(required=False, allow_blank=True)
    local_path = serializers.CharField(required=False, allow_blank=True)
    question = serializers.CharField()

    def validate(self, attrs):
        source_type = attrs["source_type"]
        if source_type == RepositorySourceType.GITHUB and not attrs.get("repo_url"):
            raise serializers.ValidationError({"repo_url": "This field is required for GitHub repositories."})
        if source_type == RepositorySourceType.LOCAL and not attrs.get("local_path"):
            raise serializers.ValidationError({"local_path": "This field is required for local repositories."})
        return attrs


class RepositorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Repository
        fields = [
            "id",
            "source_type",
            "url",
            "name",
            "default_branch",
            "local_path",
            "commit_hash",
            "indexed_at",
            "created_at",
            "updated_at",
        ]


class FindingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Finding
        fields = [
            "id",
            "file_path",
            "line_start",
            "line_end",
            "note",
            "confidence",
            "evidence_type",
            "created_at",
        ]


class ResearchSessionSerializer(serializers.ModelSerializer):
    repository = RepositorySerializer()
    findings = FindingSerializer(many=True)

    class Meta:
        model = ResearchSession
        fields = [
            "id",
            "repository",
            "question",
            "answer",
            "status",
            "model_name",
            "total_tokens",
            "duration_ms",
            "iterations_used",
            "created_at",
            "completed_at",
            "findings",
        ]


class SessionCreateResponseSerializer(serializers.Serializer):
    session_id = serializers.IntegerField()
    repository_id = serializers.IntegerField()
    status = serializers.CharField()

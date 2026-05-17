from django.contrib import admin

from .models import Finding, ResearchSession, SummaryCache, ToolCallLog


@admin.register(ResearchSession)
class ResearchSessionAdmin(admin.ModelAdmin):
    list_display = ("id", "repository", "status", "model_name", "iterations_used", "created_at", "completed_at")
    search_fields = ("question", "answer")
    list_filter = ("status",)


@admin.register(Finding)
class FindingAdmin(admin.ModelAdmin):
    list_display = ("id", "repository", "file_path", "line_start", "line_end", "confidence", "evidence_type")
    search_fields = ("file_path", "note")
    list_filter = ("evidence_type",)


@admin.register(ToolCallLog)
class ToolCallLogAdmin(admin.ModelAdmin):
    list_display = ("id", "session", "tool_name", "duration_ms", "created_at")
    search_fields = ("tool_name", "result_summary")


@admin.register(SummaryCache)
class SummaryCacheAdmin(admin.ModelAdmin):
    list_display = ("id", "repository", "scope_type", "scope_key", "updated_at")
    search_fields = ("scope_key", "content")
    list_filter = ("scope_type",)


import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("repos", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="ResearchSession",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("question", models.TextField()),
                ("answer", models.TextField(blank=True)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("running", "Running"), ("completed", "Completed"), ("failed", "Failed")], default="pending", max_length=20)),
                ("model_name", models.CharField(blank=True, max_length=255)),
                ("total_tokens", models.PositiveIntegerField(default=0)),
                ("duration_ms", models.PositiveIntegerField(default=0)),
                ("iterations_used", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("repository", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="sessions", to="repos.repository")),
            ],
            options={"ordering": ["-created_at"]},
        ),
        migrations.CreateModel(
            name="ToolCallLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("tool_name", models.CharField(max_length=255)),
                ("arguments_json", models.JSONField(default=dict)),
                ("result_summary", models.TextField()),
                ("duration_ms", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("session", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="tool_logs", to="research.researchsession")),
            ],
            options={"ordering": ["created_at"]},
        ),
        migrations.CreateModel(
            name="Finding",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("file_path", models.CharField(max_length=1024)),
                ("line_start", models.PositiveIntegerField()),
                ("line_end", models.PositiveIntegerField()),
                ("note", models.TextField()),
                ("confidence", models.FloatField(validators=[django.core.validators.MinValueValidator(0.0), django.core.validators.MaxValueValidator(1.0)])),
                ("evidence_type", models.CharField(choices=[("direct", "Direct"), ("inferred", "Inferred"), ("cross_reference", "Cross reference")], max_length=32)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("repository", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="findings", to="repos.repository")),
                ("session", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="findings", to="research.researchsession")),
            ],
            options={"ordering": ["file_path", "line_start", "created_at"]},
        ),
        migrations.CreateModel(
            name="SummaryCache",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("scope_type", models.CharField(choices=[("repo", "Repository"), ("directory", "Directory"), ("file", "File")], max_length=20)),
                ("scope_key", models.CharField(max_length=1024)),
                ("content", models.TextField()),
                ("source_hash", models.CharField(max_length=64)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("repository", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="summaries", to="repos.repository")),
                ("session", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="summary_cache_entries", to="research.researchsession")),
            ],
            options={"ordering": ["scope_type", "scope_key"], "unique_together": {("repository", "scope_type", "scope_key", "source_hash")}},
        ),
    ]

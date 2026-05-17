from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Repository",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("source_type", models.CharField(choices=[("github", "GitHub"), ("local", "Local")], max_length=20)),
                ("url", models.URLField(blank=True)),
                ("name", models.CharField(max_length=255)),
                ("default_branch", models.CharField(blank=True, max_length=255)),
                ("local_path", models.CharField(max_length=1024)),
                ("commit_hash", models.CharField(blank=True, max_length=64)),
                ("identity_hash", models.CharField(editable=False, max_length=64, unique=True)),
                ("indexed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["-updated_at"]},
        ),
    ]

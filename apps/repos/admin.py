from django.contrib import admin

from .models import Repository


@admin.register(Repository)
class RepositoryAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "source_type", "default_branch", "indexed_at", "updated_at")
    search_fields = ("name", "url", "local_path", "identity_hash")


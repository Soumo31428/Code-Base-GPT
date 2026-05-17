from django.urls import path

from .views import RepositorySessionListView, SessionCreateView, SessionDetailView


urlpatterns = [
    path("sessions/", SessionCreateView.as_view(), name="session-create"),
    path("sessions/<int:pk>/", SessionDetailView.as_view(), name="session-detail"),
    path("repos/<int:repo_id>/sessions/", RepositorySessionListView.as_view(), name="repo-session-list"),
]

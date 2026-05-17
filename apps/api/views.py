from __future__ import annotations

from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.research.models import ResearchSession
from apps.research.services import ResearchSessionService

from .serializers import ResearchSessionSerializer, SessionCreateResponseSerializer, SessionCreateSerializer


class SessionCreateView(APIView):
    service = ResearchSessionService()

    def post(self, request):
        serializer = SessionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = self.service.create_session(**serializer.validated_data)
        response = SessionCreateResponseSerializer(
            {
                "session_id": result.session.id,
                "repository_id": result.repository.id,
                "status": result.session.status,
            }
        )
        return Response(response.data, status=status.HTTP_202_ACCEPTED)


class SessionDetailView(generics.RetrieveAPIView):
    serializer_class = ResearchSessionSerializer
    queryset = ResearchSession.objects.select_related("repository").prefetch_related("findings")

    def get_object(self):
        return ResearchSessionService().get_session(self.kwargs["pk"])


class RepositorySessionListView(generics.ListAPIView):
    serializer_class = ResearchSessionSerializer

    def get_queryset(self):
        return ResearchSessionService().list_repository_sessions(self.kwargs["repo_id"]).prefetch_related("findings")

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import IsOwnerOrStaff
from apps.users.models import User

from . import queries
from .serializers import SummarySerializer, TrendsSerializer, UserSummarySerializer

MAX_DAYS = 365
MAX_LIMIT = 50


def _int_param(raw, default, maximum):
    try:
        value = int(raw) if raw is not None else default
    except (TypeError, ValueError):
        value = default
    return max(1, min(value, maximum))


class SummaryView(APIView):
    """GET /analytics/summary/ — platform-wide usage and engagement."""

    permission_classes = [IsAuthenticated]

    @extend_schema(responses=SummarySerializer, summary="Overall usage and engagement stats")
    def get(self, request):
        return Response(SummarySerializer(queries.summary()).data)


class TrendsView(APIView):
    """GET /analytics/trends/?days=7&limit=10"""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        parameters=[
            OpenApiParameter("days", int, description="Look-back window (default 7)"),
            OpenApiParameter("limit", int, description="Rows per list (default 10)"),
        ],
        responses=TrendsSerializer,
        summary="Trending genres, artists and tracks across all users",
    )
    def get(self, request):
        days = _int_param(request.query_params.get("days"), 7, MAX_DAYS)
        limit = _int_param(request.query_params.get("limit"), 10, MAX_LIMIT)
        return Response(TrendsSerializer(queries.trends(days=days, limit=limit)).data)


class UserSummaryView(APIView):
    """GET /analytics/user/{user_id}/ — owner or staff."""

    permission_classes = [IsOwnerOrStaff]

    @extend_schema(responses=UserSummarySerializer, summary="Engagement summary for one user")
    def get(self, request, user_id):
        user = get_object_or_404(User, pk=user_id)
        return Response(UserSummarySerializer(queries.user_summary(user)).data)

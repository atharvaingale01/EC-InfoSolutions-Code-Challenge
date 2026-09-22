from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.response import Response

from apps.core.permissions import IsOwnerOrStaff
from apps.core.throttles import RefreshThrottle
from apps.users.models import User

from .models import Recommendation
from .serializers import (
    RecommendationListSerializer,
    RecommendationPendingSerializer,
    RefreshAcceptedSerializer,
)
from .tasks import cache_payload, recs_cache_key, refresh_user_recommendations

PENDING_DEDUPE_WINDOW = timedelta(minutes=2)


@extend_schema(
    request=None,
    responses={202: RefreshAcceptedSerializer},
    summary="Trigger an async refresh of the user's recommendations",
)
@api_view(["POST"])
@permission_classes([IsOwnerOrStaff])
@throttle_classes([RefreshThrottle])
def refresh_recommendations(request, user_id):
    """POST /recommendations/{user_id}/refresh/ — queue a background rebuild (202)."""
    user = get_object_or_404(User, pk=user_id, is_active=True)

    recent_pending = (
        Recommendation.objects.filter(
            user=user,
            status=Recommendation.Status.PENDING,
            created_at__gte=timezone.now() - PENDING_DEDUPE_WINDOW,
        )
        .order_by("-created_at")
        .first()
    )
    if recent_pending:
        payload = {
            "recommendation_id": recent_pending.id,
            "task_id": recent_pending.task_id,
            "status": "pending",
        }
        return Response(payload, status=status.HTTP_202_ACCEPTED)

    rec = Recommendation.objects.create(user=user)
    result = refresh_user_recommendations.delay(str(user.pk), str(rec.pk))
    task_id = getattr(result, "id", None)
    if task_id:
        Recommendation.objects.filter(pk=rec.pk, task_id__isnull=True).update(task_id=task_id)
    rec.refresh_from_db()

    payload = {"recommendation_id": rec.id, "task_id": task_id, "status": rec.status}
    return Response(payload, status=status.HTTP_202_ACCEPTED)


@extend_schema(
    parameters=[
        OpenApiParameter(
            "limit", int, description=f"Max tracks (default {settings.RECS_DEFAULT_LIMIT})"
        )
    ],
    responses={
        200: RecommendationListSerializer,
        202: RecommendationPendingSerializer,
        404: OpenApiResponse(description="No recommendations generated yet"),
    },
    summary="Retrieve the user's cached recommendations",
)
@api_view(["GET"])
@permission_classes([IsOwnerOrStaff])
def recommendation_list(request, user_id):
    """GET /recommendations/{user_id}/ — cached track list (Redis -> DB)."""
    get_object_or_404(User, pk=user_id)
    limit = _parse_limit(request.query_params.get("limit"))

    cached = cache.get(recs_cache_key(user_id))
    if cached:
        return Response(_shape(user_id, cached, limit, cached=True))

    latest_ready = (
        Recommendation.objects.filter(user_id=user_id, status=Recommendation.Status.READY)
        .order_by("-completed_at")
        .first()
    )
    if latest_ready:
        payload = cache_payload(latest_ready)
        cache.set(recs_cache_key(user_id), payload, settings.RECS_CACHE_TTL_SECONDS)
        return Response(_shape(user_id, payload, limit, cached=False))

    pending = (
        Recommendation.objects.filter(user_id=user_id, status=Recommendation.Status.PENDING)
        .order_by("-created_at")
        .first()
    )
    if pending:
        return Response(
            {"status": "pending", "recommendation_id": pending.id},
            status=status.HTTP_202_ACCEPTED,
        )

    latest_failed = (
        Recommendation.objects.filter(user_id=user_id, status=Recommendation.Status.FAILED)
        .order_by("-completed_at")
        .first()
    )
    hint = f"POST /recommendations/{user_id}/refresh/ to generate them."
    if latest_failed:
        detail = f"Last refresh failed: {latest_failed.error} {hint}"
    else:
        detail = f"No recommendations yet. {hint}"
    return Response({"detail": detail}, status=status.HTTP_404_NOT_FOUND)


def _parse_limit(raw) -> int:
    try:
        limit = int(raw) if raw is not None else settings.RECS_DEFAULT_LIMIT
    except (TypeError, ValueError):
        limit = settings.RECS_DEFAULT_LIMIT
    return max(1, min(limit, settings.RECS_MAX_LIMIT))


def _shape(user_id, payload: dict, limit: int, cached: bool) -> dict:
    tracks = payload.get("tracks", [])[:limit]
    return {
        "user_id": user_id,
        "recommendation_id": payload.get("recommendation_id"),
        "generated_at": payload.get("generated_at"),
        "source": payload.get("source", "search_v1"),
        "cached": cached,
        "count": len(tracks),
        "tracks": tracks,
    }

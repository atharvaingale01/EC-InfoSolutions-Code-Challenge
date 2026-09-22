from django.core.cache import cache
from django.db import connection
from drf_spectacular.utils import OpenApiResponse, extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
    throttle_classes,
)
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

HealthSerializer = inline_serializer(
    "Health",
    fields={
        "status": serializers.CharField(),
        "checks": inline_serializer(
            "HealthChecks",
            fields={"database": serializers.BooleanField(), "cache": serializers.BooleanField()},
        ),
    },
)


@extend_schema(
    responses={
        200: HealthSerializer,
        503: OpenApiResponse(HealthSerializer, description="Degraded"),
    },
    summary="Liveness and dependency check",
)
@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
@throttle_classes([])
def health(request):
    """GET /health/ — liveness + dependency check used by the compose healthcheck."""
    checks = {"database": _check_db(), "cache": _check_cache()}
    healthy = all(checks.values())
    return Response(
        {"status": "ok" if healthy else "degraded", "checks": checks},
        status=status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE,
    )


def _check_db() -> bool:
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return True
    except Exception:
        return False


def _check_cache() -> bool:
    try:
        cache.set("health:ping", "pong", 5)
        return cache.get("health:ping") == "pong"
    except Exception:
        return False

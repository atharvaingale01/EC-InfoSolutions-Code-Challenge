from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.core.throttles import ActivityThrottle

from .serializers import UserActivitySerializer


@extend_schema(
    request=UserActivitySerializer,
    responses={201: UserActivitySerializer},
    summary="Record a play / like / skip for the authenticated user",
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@throttle_classes([ActivityThrottle])
def activity_create(request):
    """POST /activity/ — the acting user always comes from the credentials."""
    serializer = UserActivitySerializer(data=request.data, context={"request": request})
    serializer.is_valid(raise_exception=True)
    serializer.save()
    return Response(serializer.data, status=status.HTTP_201_CREATED)

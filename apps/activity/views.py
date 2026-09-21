from drf_spectacular.utils import extend_schema
from rest_framework import generics
from rest_framework.permissions import IsAuthenticated

from apps.core.throttles import ActivityThrottle

from .serializers import UserActivitySerializer


@extend_schema(summary="Record a play / like / skip for the authenticated user")
class ActivityCreateView(generics.CreateAPIView):
    """POST /activity/"""

    serializer_class = UserActivitySerializer
    permission_classes = [IsAuthenticated]
    throttle_classes = [ActivityThrottle]

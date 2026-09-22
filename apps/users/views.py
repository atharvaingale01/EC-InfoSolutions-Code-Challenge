from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle

from apps.core.permissions import IsOwnerOrStaff

from .models import User
from .serializers import ProfileSerializer, RegisterSerializer
from .services import on_preferences_changed


@extend_schema(
    request=RegisterSerializer,
    responses={
        201: OpenApiResponse(ProfileSerializer, description="Registered"),
        200: OpenApiResponse(ProfileSerializer, description="Profile updated"),
    },
    summary="Register (anonymous) or update own profile (authenticated)",
)
@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([AnonRateThrottle, UserRateThrottle])
def user_create_or_update(request):
    """
    POST /users/

    * Anonymous request     -> register a new user (201).
    * Authenticated request -> partial update of the caller's own profile (200).

    Either path invalidates cached recommendations and queues a rebuild.
    """
    if request.user.is_authenticated:
        serializer = ProfileSerializer(request.user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        on_preferences_changed(user)
        return Response(ProfileSerializer(user).data, status=status.HTTP_200_OK)

    serializer = RegisterSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    user = serializer.save()
    on_preferences_changed(user)
    return Response(ProfileSerializer(user).data, status=status.HTTP_201_CREATED)


@extend_schema(responses=ProfileSerializer, summary="Retrieve a user's profile and preferences")
@api_view(["GET"])
@permission_classes([IsOwnerOrStaff])
def user_detail(request, user_id):
    """GET /users/{user_id}/ — owner or staff only."""
    user = get_object_or_404(User, pk=user_id)
    return Response(ProfileSerializer(user).data)

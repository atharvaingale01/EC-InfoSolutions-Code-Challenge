from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import generics, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle

from apps.core.permissions import IsOwnerOrStaff

from .models import User
from .serializers import ProfileSerializer, RegisterSerializer
from .services import on_preferences_changed


class UserCreateOrUpdateView(generics.GenericAPIView):
    """
    POST /users/

    * Anonymous request  -> register a new user (201).
    * Authenticated request -> update the caller's own profile/preferences (200).

    Either path triggers a background recommendation refresh.
    """

    permission_classes = [AllowAny]
    throttle_classes = [AnonRateThrottle, UserRateThrottle]

    def get_serializer_class(self):
        if self.request.user and self.request.user.is_authenticated:
            return ProfileSerializer
        return RegisterSerializer

    @extend_schema(
        request=RegisterSerializer,
        responses={
            201: OpenApiResponse(ProfileSerializer, description="Registered"),
            200: OpenApiResponse(ProfileSerializer, description="Profile updated"),
        },
        summary="Register (anonymous) or update own profile (authenticated)",
    )
    def post(self, request):
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


class UserDetailView(generics.RetrieveAPIView):
    """GET /users/{user_id}/ — owner or staff only."""

    queryset = User.objects.all()
    serializer_class = ProfileSerializer
    permission_classes = [IsOwnerOrStaff]
    lookup_url_kwarg = "user_id"

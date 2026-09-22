"""
Function-based wrappers around SimpleJWT's serializers.

SimpleJWT ships class-based views; these expose the same behaviour as plain
functions so every route in the project is a function-based view.
"""

from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.decorators import (
    api_view,
    permission_classes,
    throttle_classes,
)
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer, TokenRefreshSerializer


# Default authentication classes are kept on purpose: DRF answers a failed
# credential check with 401 (+ WWW-Authenticate) only when an authenticator
# that defines an authenticate header is configured.
def _run(serializer_class, request):
    serializer = serializer_class(data=request.data, context={"request": request})
    try:
        serializer.is_valid(raise_exception=True)
    except TokenError as exc:
        raise InvalidToken(exc.args[0]) from exc
    return Response(serializer.validated_data, status=status.HTTP_200_OK)


TokenPairResponse = inline_serializer(
    "TokenPair", fields={"access": serializers.CharField(), "refresh": serializers.CharField()}
)
AccessTokenResponse = inline_serializer("AccessToken", fields={"access": serializers.CharField()})


@extend_schema(
    request=TokenObtainPairSerializer,
    responses={200: TokenPairResponse},
    summary="Obtain JWT access + refresh tokens",
)
@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([AnonRateThrottle, UserRateThrottle])
def token_obtain(request):
    """POST /auth/token/ — email + password -> {access, refresh}."""
    return _run(TokenObtainPairSerializer, request)


@extend_schema(
    request=TokenRefreshSerializer,
    responses={200: AccessTokenResponse},
    summary="Refresh a JWT access token",
)
@api_view(["POST"])
@permission_classes([AllowAny])
@throttle_classes([AnonRateThrottle, UserRateThrottle])
def token_refresh(request):
    """POST /auth/token/refresh/ — refresh -> {access}."""
    return _run(TokenRefreshSerializer, request)

from django.urls import path

from . import auth_views

urlpatterns = [
    path("token/", auth_views.token_obtain, name="token-obtain"),
    path("token/refresh/", auth_views.token_refresh, name="token-refresh"),
]

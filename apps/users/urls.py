from django.urls import path

from .views import UserCreateOrUpdateView, UserDetailView

urlpatterns = [
    path("", UserCreateOrUpdateView.as_view(), name="user-create-or-update"),
    path("<uuid:user_id>/", UserDetailView.as_view(), name="user-detail"),
]

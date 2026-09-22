from django.urls import path

from . import views

urlpatterns = [
    path("", views.user_create_or_update, name="user-create-or-update"),
    path("<uuid:user_id>/", views.user_detail, name="user-detail"),
]

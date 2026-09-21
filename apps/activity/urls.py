from django.urls import path

from .views import ActivityCreateView

urlpatterns = [
    path("", ActivityCreateView.as_view(), name="activity-create"),
]

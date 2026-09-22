from django.urls import path

from . import views

urlpatterns = [
    path("summary/", views.summary, name="analytics-summary"),
    path("trends/", views.trends, name="analytics-trends"),
    path("user/<uuid:user_id>/", views.user_summary, name="analytics-user"),
]

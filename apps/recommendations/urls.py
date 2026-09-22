from django.urls import path

from . import views

urlpatterns = [
    path("<uuid:user_id>/", views.recommendation_list, name="recommendation-list"),
    path("<uuid:user_id>/refresh/", views.refresh_recommendations, name="recommendation-refresh"),
]

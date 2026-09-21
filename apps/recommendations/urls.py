from django.urls import path

from .views import RecommendationListView, RefreshRecommendationsView

urlpatterns = [
    path("<uuid:user_id>/", RecommendationListView.as_view(), name="recommendation-list"),
    path(
        "<uuid:user_id>/refresh/",
        RefreshRecommendationsView.as_view(),
        name="recommendation-refresh",
    ),
]

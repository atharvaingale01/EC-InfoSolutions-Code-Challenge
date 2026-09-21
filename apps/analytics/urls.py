from django.urls import path

from .views import SummaryView, TrendsView, UserSummaryView

urlpatterns = [
    path("summary/", SummaryView.as_view(), name="analytics-summary"),
    path("trends/", TrendsView.as_view(), name="analytics-trends"),
    path("user/<uuid:user_id>/", UserSummaryView.as_view(), name="analytics-user"),
]

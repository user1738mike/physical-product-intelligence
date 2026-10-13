from django.urls import path
from drf_spectacular.views import SpectacularAPIView

from operations.views import LiveView, ReadyView

urlpatterns = [
    path("api/v1/health/live/", LiveView.as_view(), name="health-live"),
    path("api/v1/health/ready/", ReadyView.as_view(), name="health-ready"),
    path("api/v1/schema/", SpectacularAPIView.as_view(), name="schema"),
]

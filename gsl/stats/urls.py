from django.urls import path

from .views import CollectiviteDetailView, CollectiviteListView

app_name = "gsl_stats"

urlpatterns = [
    path("", CollectiviteListView.as_view(), name="collectivite-list"),
    path("<str:siren>/", CollectiviteDetailView.as_view(), name="collectivite-detail"),
]

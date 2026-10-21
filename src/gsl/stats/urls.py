from django.urls import path

from .views import CollectiviteFicoView

app_name = "gsl_stats"

urlpatterns = [
    path("", CollectiviteFicoView.as_view(), name="collectivite-fico"),
    path("<str:siren>/", CollectiviteFicoView.as_view(), name="collectivite-fico"),
]

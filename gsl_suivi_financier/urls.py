from django.urls import path

from .views import BeneficiaireDetailView, BeneficiaireListView

app_name = "gsl_suivi_financier"

urlpatterns = [
    path("", BeneficiaireListView.as_view(), name="beneficiaire-list"),
    path("<str:siren>/", BeneficiaireDetailView.as_view(), name="beneficiaire-detail"),
]

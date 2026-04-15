from django.urls import path

from gsl_ds_proxy import views

urlpatterns = [
    path("graphql/", views.graphql_proxy, name="graphql-proxy"),
]

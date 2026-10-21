from django.urls import path

from dn.proxy import views

urlpatterns = [
    path("graphql/", views.graphql_proxy, name="graphql-proxy"),
]

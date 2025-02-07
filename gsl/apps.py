from django.contrib.admin.apps import AdminConfig


class GslAdminConfig(AdminConfig):
    default_site = "gsl.admin.GslAdminSite"

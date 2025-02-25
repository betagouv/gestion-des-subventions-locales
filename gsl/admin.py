from django.conf import settings
from django.contrib import admin


class GslAdminSite(admin.AdminSite):
    site_title = "Admin GSL"
    site_header = f"{settings.VIMA_ENV_NAME} GSL - Administration"

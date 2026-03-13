from django.conf import settings


def export_vars(request):
    data = {}
    data["ENV"] = settings.ENV
    data["MATOMO_SITE_ID"] = settings.MATOMO_SITE_ID
    return data

from config import settings


def export_vars(request):
    data = {}
    data["ENV"] = settings.ENV
    return data

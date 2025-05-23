import os


def export_vars(request):
    data = {}
    data["ENV"] = os.environ["ENV"]
    return data

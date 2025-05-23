import os


def export_vars(request):
    data = {}
    print("export_vars")
    print("export_vars")
    print(os.environ)
    print(os.environ["ENV"])
    data["ENV"] = os.environ["ENV"]
    return data

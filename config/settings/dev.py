from config.settings.default import *  # noqa

DEBUG = True

ALLOWED_HOSTS = ["localhost", "127.0.0.1", "localhost:8000", "127.0.0.1:8000"]

INSTALLED_APPS.append("query_counter")  # noqa: F405
MIDDLEWARE.append("query_counter.middleware.DjangoQueryCounterMiddleware")  # noqa: F405

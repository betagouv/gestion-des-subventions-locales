from config.settings.default import *  # noqa

DEBUG = True

INSTALLED_APPS.append("query_counter")  # noqa: F405
MIDDLEWARE.append("query_counter.middleware.DjangoQueryCounterMiddleware")  # noqa: F405

import logging
import os
import sys

from config.settings.default import *  # noqa

DEBUG = True

ALLOWED_HOSTS = ["localhost", "127.0.0.1", "localhost:8000", "127.0.0.1:8000"]

INSTALLED_APPS.append("query_counter")  # noqa: F405
MIDDLEWARE.append("query_counter.middleware.DjangoQueryCounterMiddleware")  # noqa: F405

LOGGING_LEVEL = os.getenv("LOGGING_LEVEL", logging.INFO)
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "%(asctime)s %(name)-12s %(levelname)-8s %(message)s",
        },
    },
    "handlers": {
        "console": {
            "level": LOGGING_LEVEL,
            "class": "logging.StreamHandler",
            "stream": sys.stdout,
            "formatter": "verbose",
        },
    },
    "loggers": {
        "": {
            "handlers": ["console"],
            "level": LOGGING_LEVEL,
            "propagate": True,
        },
    },
}

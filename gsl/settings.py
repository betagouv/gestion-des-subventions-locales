"""
Django settings for gsl project.

Generated by 'django-admin startproject' using Django 5.1.1.

For more information on this file, see
https://docs.djangoproject.com/en/5.1/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/5.1/ref/settings/
"""

import os
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

load_dotenv()  # take environment variables from .env.

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.1/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv("SECRET_KEY")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.getenv("DEBUG")

# We support a comma-separated list of allowed hosts.
ENV_SEPARATOR = ","
ALLOWED_HOSTS = os.getenv("ALLOWED_HOSTS", "localhost").split(ENV_SEPARATOR)

# Init Sentry if the DSN is defined
SENTRY_DSN = os.getenv("SENTRY_DSN", None)
if SENTRY_DSN:
    import logging

    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.integrations.logging import LoggingIntegration

    SENTRY_ENV = os.getenv("SENTRY_ENV", "unknown")
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[
            DjangoIntegration(),
            LoggingIntegration(level=logging.ERROR, event_level=logging.ERROR),
        ],
        environment=SENTRY_ENV,
    )

# Application definition

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "mozilla_django_oidc",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_celery_results",
    "django_celery_beat",
    # dependencies:
    "widget_tweaks",
    "dsfr",
    # gsl apps:
    "gsl_core",
    "gsl_demarches_simplifiees",
    "gsl_projet",
    "gsl_pages",
    "gsl_oidc",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "gsl_oidc.middleware.LoginRequiredMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

AUTHENTICATION_BACKENDS = [
    "gsl_oidc.backends.OIDCAuthenticationBackend",
    "django.contrib.auth.backends.ModelBackend",
]

AUTH_USER_MODEL = "gsl_core.Collegue"
ROOT_URLCONF = "gsl.urls"
LANGUAGE_CODE = "fr"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "dsfr.context_processors.site_config",
            ],
        },
    },
]

WSGI_APPLICATION = "gsl.wsgi.application"

STATIC_URL = "/static/"
STATIC_ROOT = os.getenv("STATIC_ROOT", BASE_DIR / "static")

MEDIA_URL = "/media/"
MEDIA_ROOT = os.getenv("MEDIA_ROOT", BASE_DIR / "media")


# Database
# https://docs.djangoproject.com/en/5.1/ref/settings/#databases

DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL:
    DATABASES = {
        "default": dj_database_url.parse(
            DATABASE_URL,
            conn_max_age=600,
            conn_health_checks=True,
        )
    }
else:
    raise ValueError("Please set the DATABASE_URL environment variable")

# Password validation
# https://docs.djangoproject.com/en/4.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Internationalization
# https://docs.djangoproject.com/en/4.1/topics/i18n/

LANGUAGE_CODE = "fr-fr"

TIME_ZONE = "UTC"

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/4.1/howto/static-files/

STATIC_URL = "static/"


# Default primary key field type
# https://docs.djangoproject.com/en/4.1/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Connection to Démarches simplifiées’ API
DS_API_TOKEN = os.getenv("DS_API_TOKEN", "")
DS_API_URL = os.getenv(
    "DS_API_URL", "https://www.demarches-simplifiees.fr/api/v2/graphql"
)

LOGIN_URL = "/comptes/login/"

# Redirect after login/logout - used by OIDC backends

LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"

# Connection to "Pro Connect" (OIDC)

OIDC_RP_SIGN_ALGO = "RS256"
OIDC_OP_JWKS_ENDPOINT = os.getenv("PROCONNECT_JWKS_ENDPOINT")
OIDC_RP_CLIENT_ID = os.getenv("PROCONNECT_CLIENT_ID")
OIDC_RP_CLIENT_SECRET = os.getenv("PROCONNECT_CLIENT_SECRET")
OIDC_RP_SCOPES = "openid email given_name usual_name uid siret idp_id"
OIDC_OP_AUTHORIZATION_ENDPOINT = os.getenv("PROCONNECT_AUTHORIZATION_ENDPOINT")
OIDC_OP_TOKEN_ENDPOINT = os.getenv("PROCONNECT_TOKEN_ENDPOINT")
OIDC_OP_USER_ENDPOINT = os.getenv("PROCONNECT_USER_ENDPOINT")

OIDC_OP_LOGOUT_ENDPOINT = os.getenv("PROCONNECT_SESSION_END")

OIDC_AUTH_REQUEST_EXTRA_PARAMS = {"acr_values": "eidas1"}
OIDC_RENEW_ID_TOKEN_EXPIRY_SECONDS = 4 * 60 * 60
OIDC_STORE_ID_TOKEN = True
ALLOW_LOGOUT_GET_METHOD = True

# Celery configuration

CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379")
CELERY_ACCEPT_CONTENT = {"application/json"}
CELERY_RESULT_SERIALIZER = "json"
CELERY_TASK_SERIALIZER = "json"
CELERY_TIMEZONE = "Europe/Paris"
CELERY_RESULT_BACKEND = "django-db"
CELERY_RESULT_EXTENDED = True

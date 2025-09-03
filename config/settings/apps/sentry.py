# Init Sentry if the DSN is defined
import os

SENTRY_DSN = os.getenv("SENTRY_DSN", None)
if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration

    SENTRY_ENV = os.getenv("SENTRY_ENV", "unknown")
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[
            DjangoIntegration(),
        ],
        environment=SENTRY_ENV,
        enable_logs=True,
    )

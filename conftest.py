import pytest

pytest_plugins = ("celery.contrib.pytest",)


@pytest.fixture(autouse=True)
def celery_eager_mode(settings):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    settings.CELERY_TASK_EAGER_PROPAGATES = True

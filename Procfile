postdeploy: python manage.py migrate
web: bash bin/start.sh
worker: celery --app gsl worker --beat --loglevel INFO --scheduler django_celery_beat.schedulers:DatabaseScheduler

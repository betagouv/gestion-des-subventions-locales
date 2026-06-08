postdeploy: python manage.py migrate && python manage.py configure_s3_bucket
web: bash bin/start.sh
worker: celery --app gsl worker --beat --loglevel INFO --scheduler django_celery_beat.schedulers:DatabaseScheduler

#!/bin/bash

gunicorn --pythonpath src gsl.wsgi --log-file - --timeout "${GUNICORN_TIMEOUT:-30}"
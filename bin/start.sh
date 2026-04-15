#!/bin/bash

gunicorn gsl.wsgi --log-file - --timeout "${GUNICORN_TIMEOUT:-30}"
#!/bin/bash

gunicorn gsl.wsgi --log-file - --timeout 120
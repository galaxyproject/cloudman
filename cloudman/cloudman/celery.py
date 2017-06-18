# File based on:
# http://docs.celeryproject.org/en/latest/django/first-steps-with-django.html
from __future__ import absolute_import

import os

from celery import Celery
from django.conf import settings  # noqa


# set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cloudman.settings')

app = Celery('cloudman')

# Using a string here means the worker don't have to serialize
# the configuration object to child processes.
# Changed to use dedicated celery config as detailed in:
# http://docs.celeryproject.org/en/latest/getting-started/first-steps-with-celery.html
# - namespace='CELERY' means all celery-related configuration keys
#   should have a `CELERY_` prefix.
# app.config_from_object('django.conf:settings', namespace='CELERY')
app.config_from_object('cloudman.celeryconfig')

# Load task modules from all registered Django app configs.
app.autodiscover_tasks()


@app.task(bind=True)
def debug_task(self):
    print('Request: {0!r}'.format(self.request))

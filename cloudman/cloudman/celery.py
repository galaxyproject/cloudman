# File based on:
# http://docs.celeryproject.org/en/latest/django/first-steps-with-django.html
from __future__ import absolute_import

import os

import celery
from django.conf import settings  # noqa

import logging
log = logging.getLogger(__name__)

# set the default Django settings module for the 'celery' program.
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'cloudman.settings')

# Set default configuration module name
os.environ.setdefault('CELERY_CONFIG_MODULE', 'cloudlaunchserver.celeryconfig')


class Celery(celery.Celery):

    def on_configure(self):
        pass


app = Celery('proj')
# Changed to use dedicated celery config as detailed in:
# http://docs.celeryproject.org/en/latest/getting-started/first-steps-with-celery.html
# app.config_from_object('django.conf:settings')
app.config_from_envvar('CELERY_CONFIG_MODULE')
app.autodiscover_tasks(lambda: settings.INSTALLED_APPS)

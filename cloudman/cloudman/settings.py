"""
Django settings for cloudman project.
"""
from cloudlaunchserver.settings import *


# Application definition
INSTALLED_APPS += [
    'cmcluster'
]

ROOT_URLCONF = 'cloudman.urls'

WSGI_APPLICATION = 'cloudman.wsgi.application'

# Allow settings to be overridden in a cloudman/settings_local.py
try:
    from cloudman.settings_local import *  # noqa
except ImportError:
    pass

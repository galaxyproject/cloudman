"""
Django settings for cloudman project.
"""
from cloudlaunchserver.settings import *


DEBUG = True

# Application definition
INSTALLED_APPS += [
    'bossoidc',
    'djangooidc',
    'cmcluster',
    'helmsman'
]

AUTHENTICATION_BACKENDS += [
    'django.contrib.auth.backends.ModelBackend',
    'bossoidc.backend.OpenIdConnectBackend'
]

REST_FRAMEWORK['DEFAULT_AUTHENTICATION_CLASSES'] = (
        'rest_framework.authentication.SessionAuthentication',
        'rest_framework.authentication.TokenAuthentication',
        'oidc_auth.authentication.BearerTokenAuthentication',
    )

# KeyCloak realm url
auth_uri = os.environ.get("OIDC_AUTH_URI") or "http://localhost:8080/auth/realms/master"
# Client ID configured in the Auth Server
client_id = os.environ.get("OIDC_CLIENT_ID") or "cloudman"
# URL of the client 
public_uri = os.environ.get("OIDC_PUBLIC_URI") or "http://localhost:4200/cloudman"

OIDC_ALLOW_DYNAMIC_OP = False

from bossoidc.settings import *

LOGIN_URL = "/cloudman/openid/openid/KeyCloak"
LOGOUT_URL = "/cloudman/openid/logout"

configure_oidc(auth_uri, client_id, public_uri)  # NOTE: scope is optional and can be left out


ROOT_URLCONF = 'cloudman.urls'

WSGI_APPLICATION = 'cloudman.wsgi.application'


CLOUDLAUNCH_PATH_PREFIX = os.environ.get('CLOUDLAUNCH_PATH_PREFIX', '/cloudlaunch')
STATIC_URL = CLOUDLAUNCH_PATH_PREFIX + '/static/'
REST_SCHEMA_BASE_URL = CLOUDLAUNCH_PATH_PREFIX + '/'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.' + os.environ.get('CLOUDMAN_DB_ENGINE', 'sqlite3'),
        'NAME': os.environ.get('CLOUDMAN_DB_NAME', os.path.join(BASE_DIR, 'db.sqlite3')),
         # The following settings are not used with sqlite3:
        'USER': os.environ.get('CLOUDMAN_DB_USER'),
        'HOST': os.environ.get('CLOUDMAN_DB_HOST'), # Empty for localhost through domain sockets or '127.0.0.1' for localhost through TCP.
        'PORT': os.environ.get('CLOUDMAN_DB_PORT'), # Set to empty string for default.
        'PASSWORD': os.environ.get('CLOUDMAN_DB_PASSWORD'),
    }
}

# Allow settings to be overridden in a cloudman/settings_local.py
try:
    from cloudman.settings_local import *  # noqa
except ImportError:
    pass

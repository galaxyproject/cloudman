"""
Django settings for cloudman project.
"""
from cloudlaunchserver.settings import *
from cloudman.auth import get_from_well_known

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Absolute path to the directory static files should be collected to.
# Don't put anything in this directory yourself; store your static files
# in apps' "static/" subdirectories and in STATICFILES_DIRS.
# Example: "/var/www/example.com/static/"
STATIC_ROOT = os.path.join(BASE_DIR, 'static')

# Application definition
INSTALLED_APPS += [
    'mozilla_django_oidc',
    'clusterman',
    'helmsman.apps.HelmsManConfig',
    'projman',
    # Discover and apply permission rules in each project
    'rules.apps.AutodiscoverRulesConfig'
]

AUTHENTICATION_BACKENDS = [
    'rules.permissions.ObjectPermissionBackend',
    'django.contrib.auth.backends.ModelBackend',
    'cloudman.oidc.CMOIDCAuthenticationBackend'
]

MIDDLEWARE += [
    'mozilla_django_oidc.middleware.SessionRefresh'
]

REST_FRAMEWORK['DEFAULT_AUTHENTICATION_CLASSES'] += ('mozilla_django_oidc.contrib.drf.OIDCAuthentication',)

OIDC_ENABLED = os.environ.get('OIDC_ENABLED', False)

# OIDC settings. Set only if OIDC_ENABLED
OIDC_RP_CLIENT_ID = "cloudman"
OIDC_RP_CLIENT_SECRET = None
OIDC_OP_AUTHORIZATION_ENDPOINT = "http://localhost:8080/auth/realms/master/.well-known/openid-configuration"
OIDC_OP_TOKEN_ENDPOINT = "dummy"
OIDC_OP_USER_ENDPOINT = "dummy"
OIDC_OP_JWKS_ENDPOINT = "dummy"
OIDC_RP_SIGN_ALGO = "RS256"

if OIDC_ENABLED:
    # KeyCloak realm url
    OIDC_OP_METADATA_ENDPOINT = os.environ.get(
        "OIDC_AUTH_URI") or "http://localhost:8080/auth/realms/master/.well-known/openid-configuration"
    # Client ID configured in the Auth Server
    OIDC_RP_CLIENT_ID = os.environ.get("OIDC_CLIENT_ID") or "cloudman"
    OIDC_RP_CLIENT_SECRET = os.environ.get("OIDC_CLIENT_SECRET")
    OIDC_OP_AUTHORIZATION_ENDPOINT = get_from_well_known(OIDC_OP_METADATA_ENDPOINT, 'authorization_endpoint')
    OIDC_OP_TOKEN_ENDPOINT = get_from_well_known(OIDC_OP_METADATA_ENDPOINT, 'token_endpoint')
    OIDC_OP_USER_ENDPOINT = get_from_well_known(OIDC_OP_METADATA_ENDPOINT, 'userinfo_endpoint')
    OIDC_OP_JWKS_ENDPOINT = get_from_well_known(OIDC_OP_METADATA_ENDPOINT, 'jwks_uri')
    OIDC_RP_SIGN_ALGO = os.environ.get("OIDC_SIGN_ALGO") or "RS256"
    OIDC_USERNAME_ALGO = lambda claim: claim
    OIDC_OP_LOGOUT_URL_METHOD = 'cloudman.oidc.provider_logout'


ROOT_URLCONF = 'cloudman.urls'

WSGI_APPLICATION = 'cloudman.wsgi.application'


#CLOUDLAUNCH_PATH_PREFIX = os.environ.get('CLOUDLAUNCH_PATH_PREFIX', '')
STATIC_URL = CLOUDLAUNCH_PATH_PREFIX + '/cloudman/static/'
FORCE_SCRIPT_NAME = CLOUDLAUNCH_PATH_PREFIX
REST_SCHEMA_BASE_URL = CLOUDLAUNCH_PATH_PREFIX + "/cloudman/cloudlaunch/"

REST_AUTH_SERIALIZERS = {
    'USER_DETAILS_SERIALIZER': 'projman.serializers.UserSerializer'
}

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

CM_GLOBAL_CONTEXT_PATH = "/opt/cloudman/global_context.yaml"

if os.path.isfile(CM_GLOBAL_CONTEXT_PATH) and os.access(CM_GLOBAL_CONTEXT_PATH, os.R_OK):
    import yaml
    with open(CM_GLOBAL_CONTEXT_PATH) as f:
        print(f"Loading cloudman global context from: {CM_GLOBAL_CONTEXT_PATH}")
        CM_GLOBAL_CONTEXT = yaml.load(f)
else:
    CM_GLOBAL_CONTEXT = {}

# Allow settings to be overridden in a cloudman/settings_local.py
try:
    from cloudman.settings_local import *  # noqa
except ImportError:
    pass

#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
import re
import sys

from setuptools import setup
from setuptools import find_packages


def get_version(*file_paths):
    """Retrieves the version from cloudman/__init__.py"""
    filename = os.path.join(os.path.dirname(__file__), *file_paths)
    version_file = open(filename).read()
    version_match = re.search(r"^__version__ = ['\"]([^'\"]*)['\"]",
                              version_file, re.M)
    if version_match:
        return version_match.group(1)
    raise RuntimeError('Unable to find version string.')


version = get_version("cloudman", "cloudman", "__init__.py")


if sys.argv[-1] == 'publish':
    try:
        import wheel
        print("Wheel version: ", wheel.__version__)
    except ImportError:
        print('Wheel library missing. Please run "pip install wheel"')
        sys.exit()
    os.system('python setup.py sdist upload')
    os.system('python setup.py bdist_wheel upload')
    sys.exit()

if sys.argv[-1] == 'tag':
    print("Tagging the version on git:")
    os.system("git tag -a %s -m 'version %s'" % (version, version))
    os.system("git push --tags")
    sys.exit()

readme = open('README.rst').read()
history = open('HISTORY.rst').read().replace('.. :changelog:', '')

REQS_BASE = [
    'Django>=2.0.0,<3.0',
    # ======== Celery =========
    'celery>=4.1.0',
    # celery results backend which uses the django DB
    'django-celery-results>=1.0.1',
    # celery background task monitor which uses the django DB
    'django-celery-beat>=1.1.0',
    # ======== DRF =========
    'djangorestframework>=3.7.7',
    # pluggable social auth for django login
    'django-allauth>=0.34.0',
    # Provides nested routing for DRF
    'drf-nested-routers>=0.90.0',
    # For DRF filtering by querystring
    'django-filter>=1.1.0',
    # ======== Permissions =========
    # object level permissions for django auth
    'rules',
    # ======== CloudLaunch =========
    'cloudlaunch-server>=0.1.1',
    'cloudlaunch-cli'
]

REQS_PROD = ([
    # postgres database driver
    'psycopg2-binary',
    'gunicorn'] + REQS_BASE
)

REQS_TEST = ([
    'responses',  # For mocking responses during tests
    'tox>=2.9.1',
    'coverage>=4.4.1',
    'flake8>=3.4.1',
    'flake8-import-order>=0.13'] + REQS_BASE
)

REQS_DEV = ([
    # As celery message broker during development
    'sphinx>=1.3.1',
    'bumpversion>=0.5.3',
    'pylint-django'] + REQS_TEST
)

setup(
    name='cloudman-server',
    version=version,
    description=("CloudMan is a ReSTful, extensible Django app for"
                 " managing clusters"),
    long_description=readme + '\n\n' + history,
    author='Galaxy Project',
    author_email='help@cloudve.org',
    url='https://github.com/galaxyproject/cloudman',
    package_dir={'': 'cloudman'},
    packages=find_packages('cloudman'),
    include_package_data=True,
    install_requires=REQS_BASE,
    extras_require={
        'dev': REQS_DEV,
        'test': REQS_TEST,
        'prod': REQS_PROD
    },
    license="MIT",
    keywords='cloudman',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Framework :: Django',
        'Framework :: Django :: 2.0',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: BSD License',
        'Natural Language :: English',
        'Programming Language :: Python :: 3.6',
        'Topic :: Internet :: WWW/HTTP',
        'Topic :: Internet :: WWW/HTTP :: WSGI :: Application'
    ],
)

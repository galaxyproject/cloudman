CloudMan is a cloud infrastructure and application manager, primarily for Galaxy.

.. image:: https://coveralls.io/repos/github/galaxyproject/cloudman/badge.svg?branch=master
   :target: https://coveralls.io/github/galaxyproject/cloudman?branch=master
   :alt: Test Coverage Report

.. image:: https://travis-ci.org/galaxyproject/cloudman.svg?branch=master
   :target: https://travis-ci.org/galaxyproject/cloudman
   :alt: Travis Build Status

Installation
------------
CloudMan is intended to be installed via the `CloudMan Helm chart`_.

Run locally for development
---------------------------
.. code-block:: bash

    git clone https://github.com/galaxyproject/cloudman.git
    cd cloudman
    pip install -r requirements.txt
    python cloudman/manage.py migrate
    gunicorn --log-level debug cloudman.wsgi

The CloudMan API will be available at http://127.0.0.1:8000/cloudman/api/v1/

To add the UI, see https://github.com/cloudve/cloudman-ui

Build Docker image
------------------
To build a Docker image, run ``docker build -t galaxy/cloudman:latest .``
Push it to Dockerhub with:

.. code-block:: bash

    docker login
    docker push galaxy/cloudman:latest

.. _`CloudMan Helm chart`: https://github.com/cloudve/cloudman-helm

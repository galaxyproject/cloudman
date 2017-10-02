An all-new codebase for `CloudMan`_ - a cloud manager.

.. image:: https://coveralls.io/repos/github/galaxyproject/cloudman/badge.svg?branch=v2.0
   :target: https://coveralls.io/github/galaxyproject/cloudman?branch=v2.0
   :alt: Test Coverage Report

.. image:: https://travis-ci.org/galaxyproject/cloudman.svg?branch=v2.0
   :target: https://travis-ci.org/galaxyproject/cloudman
   :alt: Travis Build Status


To start using CloudMan
-----------------------

Note that the current version is in the early stages of development and does
not yet provide much functionality. There are multiple ways to get started.
If you would just like to run the application, try one of the container-based
approaches. If you want to develop the application, clone this repo first.
Even during development, it is advisable to run the app in a containerized
infrastructure to have a complete environment properly set up.

To use with a `Kubernetes environment`_
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
To run the app in a Kubernetes cluster, run the following commands (from
CloudMan repo base directory). If you need a local Kubernetes setup, try
`Minikube`_. You will also need to setup `Helm`_.

First clone the repo locally:

.. code-block:: bash

    git clone https://github.com/galaxyproject/cloudman.git
    cd cloudman
    git checkout v2.0

Once you have the source code available, run the following command to deploy
all the necessary components:

.. code-block:: bash

    helm install k8s/cloudman

To access the app, run the command displayed at the end of the output.

To shut everything down, we'll need to retrieve the name of the current release
and then delete it. Helm will clean up everything in a few moments.

.. code-block:: bash

    helm ls  # Get the release name
    helm del <release name>

If you wish not to use Helm, you can deploy K8S config files by hand by
executing the following commands, in this order:

.. code-block:: bash

    kubectl create -f k8s/cm-namespace.yaml
    kubectl create -f k8s/cm-configMap.yaml
    kubectl create -f k8s/cm-deployment.yaml
    kubectl create -f k8s/cm-service.yaml

To access the app, do the following:

.. code-block:: bash

    kubectl cluster-info  # Get cluster IP
    kubectl --namespace=cloudman describe svc | grep NodePort # Get the port

Access the app at http://cluster-ip:port/api/v1/

To access a running container within a K8S pod, run
``kubectl --namespace=cloudman exec -it <podName> -c <containerName> /bin/bash``
(To set the ``cloudman`` namespace as the default preference, use
``kubectl config set-context $(kubectl config current-context) --namespace=cloudman``)

To use with a `Docker environment`_
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

To run as a standalone Docker container, run
``docker run -d -p 8888:8000 afgane/cloudman ./run_web.sh``
This will make the app available on localhost port 8888.
To access a running container instance, run
``docker exec -it <container id> /bin/bash``

To use without container infrastructure
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

To run natively on the system, do

.. code-block:: bash

    git clone https://github.com/galaxyproject/cloudman.git
    cd cloudman
    git checkout v2.0
    python manage.py migrate
    gunicorn cloudman.wsgi

CloudMan will be available at http://127.0.0.1:8000/

Development
-----------

To build a Docker image locally, run ``docker build -t afgane/cloudman:latest .``
Push it to Dockerhub with:

.. code-block:: bash

    docker login
    docker push afgane/cloudman:latest


To update Chart dependencies, edit ``k8s/cloudman/requirements.yaml`` to
include a dependent chart and run ``helm dependency update k8s/cloudman/``.
Commit the dependent chart into this repo so it is ready for consumption at
deployment time.

.. _`CloudMan`: http://cloudman.irb.hr/
.. _`Kubernetes environment`: http://kubernetes.io
.. _`Minikube`: https://kubernetes.io/docs/getting-started-guides/minikube
.. _`Helm`: https://docs.helm.sh/using-helm/#quick-start
.. _`Docker environment`: https://docs.docker.com/engine

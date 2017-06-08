An all-new codebase for [CloudMan](http://cloudman.irb.hr/) - a cloud manager.

----
## To start using CloudMan

Note that the current version is in the early stages of development and does
not yet provide much functionality. There are multiple ways to get started.
If you would just like to run the application, try one of the container-based
approaches. If you want to develop the application, clone this repo first.
Even during development, it is advisable to run the app in a containerized
infrastructure to have a complete environment properly set up.

#### To use with [Kubernetes environment](http://kubernetes.io)
To run the app in a Kubernetes cluster, run the following commands (from
CloudMan repo base directory). If you need a local Kubernetes setup, try
[Minikube](https://kubernetes.io/docs/getting-started-guides/minikube).

```
kubectl create -f k8s/namespace.yaml
kubectl create -f k8s/configMap.yaml
kubectl create -f k8s/web-deployment.yaml
kubectl create -f k8s/web-service.yaml
```
This will setup the necessary container infrastructure. Now, to access the app,
do the following:
```
kubectl cluster-info  # Get cluster IP
kubectl --namespace=cloudman describe svc cm-web | grep NodePort # Get the port
```
(To set the `cloudman` namespace as the default preference, use
`kubectl config set-context $(kubectl config current-context) --namespace=cloudman`)
Access the app at http://cluster-ip:port/

To access a running container within a K8S pod, run
`kubectl --namespace=cloudman exec -it <podName> -c <containerName> /bin/bash`

#### To use with [Docker environment](https://docs.docker.com/engine)
To run as a standalone Docker container, run
`docker run -d -p 8888:8000 afgane/cloudman ./run_web.sh`
This will make the app available on localhost port 8888.
To access a running container instance, run
`docker exec -it <container id> /bin/bash`

#### To use without container infrastructure
To run natively on the system, do
```
git clone https://github.com/galaxyproject/cloudman.git && cd cloudman
git checkout v2.0
cd cloudman
python manage.py migrate
gunicorn cloudman.wsgi
```
CloudMan will be available at http://127.0.0.1:8000/

## Development

To build a Docker image locally, run `docker build -t afgane/cloudman:latest .`
Push it to Dockerhub with:
```
docker login
docker push afgane/cloudman:latest
```

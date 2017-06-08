An all-new codebase for CloudMan.

To run as a standalone Docker container, run
`docker run -d -p 8888:8000 afgane/cloudman ./run_web.sh`
This will make the app available on localhost port 8888.
To access a running container instance, run
`docker exec -it <container id> /bin/bash`

To run the app in a Kubernetes cluster, run the following commands (from
CloudMan repo base directory). If you need a local Kubernetes setup, try
[Minikube](https://kubernetes.io/docs/getting-started-guides/minikube).

```
kubectl create -f k8s/namespace.yaml
kubectl create -f k8s/web-deployment.yaml
kubectl create -f k8s/web-service.yaml
```
This will setup the necessary containers. Now, to access the app, do the
following:
```
kubectl cluster-info  # Get cluster IP
kubectl --namespace=cloudman describe svc web | grep NodePort # Get the port
```
Access the app at http://cluster-ip:port/

To access a running container within a K8S pod, run
`kubectl --namespace=cloudman exec -it <podName> -c <containerName> /bin/bash`


To run locally, do
```
git clone https://github.com/galaxyproject/cloudman.git && cd cloudman
git checkout v2.0
cd cloudman
python manage.py migrate
gunicorn cloudman.wsgi
```
CloudMan will be available at http://127.0.0.1:8000/


To build a Docker image, run `docker build -t afgane/cloudman:latest .` Push
it to Dockerhub with:
```
docker login
docker push afgane/cloudman:latest
```

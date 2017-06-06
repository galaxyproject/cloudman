An all-new codebase for CloudMan.

To run as a standalone Docker container, run
`docker run -d -p 8888:8000 afgane/cloudman ./run_web.sh`
This will make the app available on localhost port 8888.

K8S integration is coming.


To run locally, do
```
git clone https://github.com/galaxyproject/cloudman.git && cd cloudman
git checkout v2.0
python manage.py migrate
python manage.py runserver
```

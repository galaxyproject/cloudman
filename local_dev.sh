. venv/bin/activate
CONSUL_PATH="./venv/bin"
if [ ! -f $CONSUL_PATH/consul ]; then
   echo "Extracting consul to: $CONSUL_PATH"
   wget -O- https://releases.hashicorp.com/consul/0.8.4/consul_0.8.4_darwin_amd64.zip | tar xvz -C $CONSUL_PATH
fi
$CONSUL_PATH/consul agent -dev &
cd cloudman
/usr/local/Cellar/rabbitmq/3.6.9/sbin/rabbitmq-server &
celery -E -A cloudman worker -l debug &
python manage.py runserver


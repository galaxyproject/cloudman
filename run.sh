#!/bin/bash

cd `dirname $0`
conf_file="cm_wsgi.ini"
ud_file="userData.yaml"
if [ ! -f $conf_file ] || [ ! -f $ud_file ]; then
    echo "Running setup first"
    sh setup.sh
fi
python ./scripts/paster.py serve $conf_file --pid-file=cm_webapp.pid $@

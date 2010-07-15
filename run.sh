#!/bin/bash
# export PATH=/opt/galaxy/bin:/opt/ec2/bin:/usr/gnu/bin:/usr/bin:/usr/X11/bin:/usr/sbin:/sbin:/bin:$PATH

cd `dirname $0`
conf_file="cm_wsgi.ini"
if [ ! -f $conf_file ]; then
    echo "Running setup first"
    sh setup.sh
fi
python ./scripts/paster.py serve $conf_file --pid-file=cm_webapp.pid $@

#!/bin/bash
export PATH=/opt/galaxy/bin:/opt/ec2/bin:/usr/gnu/bin:/usr/bin:/usr/X11/bin:/usr/sbin:/sbin:/bin:$PATH

cd `dirname $0`
python ./scripts/paster.py serve cm_wsgi.ini --pid-file=cm_webapp.pid $@
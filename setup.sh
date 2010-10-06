#!/bin/bash

python ./scripts/check_python.py
[ $? -ne 0 ] && exit 1

SAMPLE_FILES="
cm_wsgi.ini.sample"

for sample_file in $SAMPLE_FILES; do
    file=`echo $sample_file | sed -e 's/\.sample$//'`
    if [ -f $file ]; then
        echo "Not overwriting existing $file"
    else
        echo "Copying $sample_file to $file"
        cp $sample_file $file
    fi
done

# Install (missing) required libraries
# libs=( 'mako' 'paste' 'routes' 'webhelpers' 'pastescript' 'webob' )
# for lib in ${libs[*]}; do
#     easy_install $lib
# done

ud_file="userData.yaml"
if [ ! -f $ud_file ]; then
    echo "User data file '$ud_file' not found; creating a test version of the file."
    echo "cluster_name: local test" > $ud_file
    echo "access_key: <your AWS access key>" >> $ud_file
    echo "secret_key: <your AWS private key>" >> $ud_file
    echo "cloudman_home: `pwd`" >> $ud_file
    echo "role: master" >> $ud_file
    echo "bucket_cluster: TestBucket" >> $ud_file
    echo "bucket_default: cloudman" >> $ud_file
    echo "testflag: True" >> $ud_file
fi

# RabbitMQ is having trouble starting - this seems to fix it until a new AMI is built
# /etc/init.d/rabbitmq-server stop
# if [ -d '/var/lib/rabbitmq/mnesia' ]; then
#     rm -rf /var/lib/rabbitmq/mnesia
# fi
# if [ -d '/mnesia' ]; then
#     rm -rf /mnesia
# fi
# /etc/init.d/rabbitmq-server start
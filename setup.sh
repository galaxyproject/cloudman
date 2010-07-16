#!/bin/sh

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

ud_file="userData.txt"
if [ ! -f $ud_file ]; then
    echo "User data file '$ud_file' not found; creating a test version of the file."
    echo "CLUSTER_NAME=local test" > $ud_file
    echo "AWS_ACCESS_KEY=<your AWS access key>" >> $ud_file
    echo "AWS_PRIVATE_KEY=<your AWS private key>" >> $ud_file
    echo "CM_HOME=`pwd`" >> $ud_file
    echo "ROLE=master" >> $ud_file
    echo "MASTER_IP=`hostname`" >> $ud_file
    echo "BUCKET_NAME=TestBucket" >> $ud_file
    echo "TESTFLAG=True" >> $ud_file
fi
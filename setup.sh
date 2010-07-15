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
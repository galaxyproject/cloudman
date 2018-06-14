#!/bin/bash
cd "${0%/*}"/..

echo "Apply database migrations from `pwd`"
python manage.py migrate || { echo 'migration failed. Aborting...' ; exit 1; }

# https://serverfault.com/questions/122737/in-bash-are-wildcard-expansions-guaranteed-to-be-in-order
echo "Load initial data from /app/initial_data/*.json"
python manage.py loaddata /app/initial_data/*.json

echo "Create a superuser"
cat scripts/create_superuser.py | python manage.py shell

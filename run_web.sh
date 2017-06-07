#!/bin/sh

cd cloudman

# Prepare init migration
# su -m myuser -c "python manage.py makemigrations"
# Migrate db, so we have the latest db schema
su -m myuser -c "python manage.py migrate"
# Start development server on public ip interface, on port 8000
su -m cloudman -c "gunicorn -b :8000 cloudman.wsgi"

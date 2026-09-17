#!/usr/bin/env bash
# Render build script: install, collect static files, update the database.
set -o errexit

pip install -r requirements.txt

python manage.py collectstatic --no-input
python manage.py migrate --no-input
python manage.py setup_categories

# Demo products only when LOAD_SAMPLE_DATA=True. Their photos are re-drawn on every
# deploy because Render's free disk is wiped each time (the database is not).
if [ "$LOAD_SAMPLE_DATA" = "True" ]; then
  python manage.py load_sample_data
fi
python manage.py restore_sample_images

# Admin account from DJANGO_SUPERUSER_* environment variables (skipped if it exists).
if [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
  python manage.py createsuperuser --no-input || true
fi

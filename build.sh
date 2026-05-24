#!/usr/bin/env bash
# Exit on error
set -o errexit

# Install dependencies
pip install -r requirements.txt

# Collect static files and migrate database
python manage.py collectstatic --no-input
python manage.py migrate
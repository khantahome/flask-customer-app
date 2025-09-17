#!/bin/bash
set -e

echo "Starting deployment..."
cd /var/www/flask_customer_app

git pull origin main

source venv/bin/activate
pip install -r requirements.txt

sudo systemctl restart loanapp
echo "Deployment finished successfully!"
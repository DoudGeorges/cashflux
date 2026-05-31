#!/bin/bash
# CashFlux production deploy (Flask app)
# Usage: ssh root@cashflux.tech 'bash -s' < deploy.sh

set -e

echo "=== Pulling latest code ==="
cd /opt/cashflux
git pull origin main

echo "=== Installing Python deps ==="
source venv/bin/activate
pip install -q -r requirements.txt

echo "=== Restarting CashFlux ==="
systemctl restart cashflux
sleep 2

echo "=== Verifying ==="
curl -sf http://127.0.0.1:8000/api/health || { echo "HEALTH CHECK FAILED"; exit 1; }

echo "=== Deploy complete ==="
systemctl status cashflux --no-pager | head -5

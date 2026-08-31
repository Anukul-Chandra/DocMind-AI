#!/bin/sh
set -e

echo "=== DocMind AI startup ==="
echo "PORT=${PORT:-8000}"
echo "PYTHON=$(which python)"
echo "PYTHONPATH=${PYTHONPATH:-not set}"
echo "Working dir: $(pwd)"
echo "========================"

exec python -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"

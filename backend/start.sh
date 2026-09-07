#!/bin/sh
set -e

echo "=== DocMind AI startup ==="
echo "PORT=${PORT:-8000}"
echo "PYTHON=$(which python)"
echo "PYTHONPATH=${PYTHONPATH:-not set}"
echo "Working dir: $(pwd)"
echo "========================"

# Timestamped diagnostic logging: print before/after heavy imports so if the
# container OOM-kills again we know exactly which step is slow or fatal.
# Only probe libraries that are ACTUALLY imported at real app startup (per the
# import-chain audit).  torch/sentence_transformers are lazy-loaded on first
# request — importing them here would add ~300 MB+ RSS and defeat the probe.
python -c "
import time
_t = lambda: time.strftime('%H:%M:%S')
print(f'[{_t()}] (diag) Starting Python …', flush=True)
try:
    import faiss
    print(f'[{_t()}] (diag) faiss imported OK', flush=True)
except Exception as e:
    print(f'[{_t()}] (diag) faiss import FAILED: {e}', flush=True)

try:
    import fitz
    print(f'[{_t()}] (diag) fitz (PyMuPDF) imported OK', flush=True)
except Exception as e:
    print(f'[{_t()}] (diag) fitz import FAILED: {e}', flush=True)

print(f'[{_t()}] (diag) Pre-import checks done. Launching uvicorn …', flush=True)
"

exec python -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"

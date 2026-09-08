FROM python:3.12-slim

WORKDIR /app

# Install CPU-only torch BEFORE requirements.txt so pip never pulls the
# default CUDA wheel (nvidia-cublas-cu12, nvidia-cudnn-cu12, etc.).
# This cuts the image size by ~1.5 GiB and avoids OOM on 512 MiB hosts.
COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
RUN pip install --no-cache-dir -r /app/requirements.txt

# Pre-download the embedding model so the backend can start offline.
# The image build environment has outbound internet; Render runtime may not.
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# Copy only the application package. The .env file and runtime storage/ are
# provided at runtime (env_file + volume) and are intentionally NOT baked in.
COPY backend/app /app/app
COPY backend/start.sh /app/start.sh
RUN chmod +x /app/start.sh

# Keep memory predictable on constrained hosts (e.g. Render free tier = 512Mi).
ENV OMP_NUM_THREADS=1
ENV TOKENIZERS_PARALLELISM=false

# Prevent huggingface_hub from phoning home to check model freshness on
# every SentenceTransformer load — the model is baked into the image, so
# version checks are pointless and the HEAD request can hang on slow/blocked
# egress (Render free tier).
ENV HF_HUB_OFFLINE=1

EXPOSE 8000

# Single-process mode (no --workers). The FAISS + JSON storage backend is
# process-local and must not be split across workers; single-process uvicorn
# avoids multiprocessing overhead and the --workers 1 hang.
ENTRYPOINT ["/app/start.sh"]

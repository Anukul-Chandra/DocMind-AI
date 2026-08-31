FROM python:3.12-slim

WORKDIR /app

COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy only the application package. The .env file and runtime storage/ are
# provided at runtime (env_file + volume) and are intentionally NOT baked in.
COPY backend/app /app/app
COPY backend/start.sh /app/start.sh
RUN chmod +x /app/start.sh

# Keep memory predictable on constrained hosts (e.g. Render free tier = 512Mi).
ENV OMP_NUM_THREADS=1
ENV TOKENIZERS_PARALLELISM=false

EXPOSE 8000

# Single-process mode (no --workers). The FAISS + JSON storage backend is
# process-local and must not be split across workers; single-process uvicorn
# avoids multiprocessing overhead and the --workers 1 hang.
ENTRYPOINT ["/app/start.sh"]

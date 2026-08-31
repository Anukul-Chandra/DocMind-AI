FROM python:3.12-slim

WORKDIR /app

COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy only the application package. The .env file and runtime storage/ are
# provided at runtime (env_file + volume) and are intentionally NOT baked in.
COPY backend/app /app/app

# Keep memory predictable on constrained hosts (e.g. Render free tier = 512Mi).
ENV OMP_NUM_THREADS=1
ENV TOKENIZERS_PARALLELISM=false

EXPOSE 8000

# Exactly one worker, no --reload. FAISS + JSON require a single instance.
CMD uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --workers 1

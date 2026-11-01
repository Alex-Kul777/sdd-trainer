# SDD Trainer — development image (phase 0 skeleton)
# Phase 2 will switch the default command to the FastAPI/uvicorn server.

FROM python:3.12-slim

WORKDIR /app

# Install dependencies first (better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Install the package and copy the sources
COPY . .
RUN pip install --no-cache-dir -e .

# Runtime data (training state, checkpoints) — mount or persist this dir
RUN mkdir -p data logs

EXPOSE 8000

CMD ["python", "app.py"]

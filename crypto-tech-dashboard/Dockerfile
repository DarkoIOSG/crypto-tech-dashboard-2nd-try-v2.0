FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DATA_DIR=/app/local_data \
    HOST=0.0.0.0 \
    PORT=8000

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl tzdata \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN python -m pip install --upgrade pip setuptools wheel \
    && pip install -r requirements.txt

COPY backend ./backend
COPY frontend ./frontend
COPY local_data ./local_data
COPY README.md run.sh .env.example ./

EXPOSE 8000

CMD ["sh", "-c", "python -m uvicorn backend.main:app --host ${HOST:-0.0.0.0} --port ${PORT:-8000}"]

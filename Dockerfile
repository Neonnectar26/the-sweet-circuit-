FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app

ENV DATABASE_PATH=/app/data/sweet_circuit.db \
    STRIPE_ENABLED=false \
    PORT=8000

VOLUME ["/app/data"]
EXPOSE 8000

CMD ["sh", "-c", "mkdir -p /app/data && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]

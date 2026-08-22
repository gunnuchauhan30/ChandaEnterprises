FROM python:3.12-slim

WORKDIR /app

# psycopg2-binary needs libpq at runtime; build tools kept minimal.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p uploads/invoices logs

EXPOSE 8000

# 4 workers is a reasonable default for a small/medium ERP deployment;
# tune with WEB_CONCURRENCY env var or override this CMD for your box.
CMD ["gunicorn", "app.main:app", "-k", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:8000", "--workers", "4", "--timeout", "60"]

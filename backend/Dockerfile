# Server image: FastAPI + local OCR (Tesseract, Hebrew) + barcodes (zbar) + OpenCV.
FROM python:3.12-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr libzbar0 libglib2.0-0 curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# The same OCR models as in development (tessdata_fast eng/heb + osd for page orientation), so results match.
RUN mkdir -p /opt/tessdata \
    && curl -fsSL -o /opt/tessdata/eng.traineddata https://github.com/tesseract-ocr/tessdata_fast/raw/4.1.0/eng.traineddata \
    && curl -fsSL -o /opt/tessdata/heb.traineddata https://github.com/tesseract-ocr/tessdata_fast/raw/4.1.0/heb.traineddata \
    && curl -fsSL -o /opt/tessdata/osd.traineddata https://github.com/tesseract-ocr/tessdata/raw/4.1.0/osd.traineddata

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TESSERACT_CMD=/usr/bin/tesseract \
    OCR_TESSDATA_DIR=/opt/tessdata \
    APP_DATA_DIR=/app/data

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .

RUN useradd --create-home --uid 10001 app && mkdir -p /app/data && chown -R app /app/data
USER app

EXPOSE 8000
# Migrations and the senders catalog are idempotent — safe on every start (one replica).
CMD ["sh", "-c", "alembic upgrade head && python -m db.seed_senders && exec uvicorn main:app --host 0.0.0.0 --port 8000"]

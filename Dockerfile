FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src \
    APPEAL_DEPLOYMENT=cloud_run

WORKDIR /app

COPY src ./src
COPY config ./config
COPY scripts/run_local_api.py ./scripts/run_local_api.py

RUN python -m pip install --no-cache-dir \
    "google-cloud-firestore>=2.16.0,<3.0.0" \
    "google-cloud-modelarmor>=0.7.1,<1.0.0" \
    "google-cloud-pubsub>=2.23.0,<3.0.0"

RUN useradd --create-home --uid 10001 appeal \
    && mkdir -p /tmp/appeal \
    && chown -R appeal:appeal /app /tmp/appeal

USER appeal

CMD ["sh", "-c", "exec python scripts/run_local_api.py --host 0.0.0.0 --port ${PORT:-8080} --ledger /tmp/appeal/receipts.jsonl"]

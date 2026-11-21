FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY backend/requirements-production.lock ./
RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 libgomp1 && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir -r requirements-production.lock && useradd --uid 10001 --create-home gcai
COPY backend/app ./app
COPY backend/gunicorn.conf.py ./gunicorn.conf.py
RUN mkdir -p /var/lib/gcai/artifacts && chown -R 10001:10001 /var/lib/gcai
ENV GCAI_ARTIFACT_DIR=/var/lib/gcai/artifacts
USER 10001:10001
CMD ["gunicorn", "--config", "gunicorn.conf.py", "app:create_app()"]

FROM python:3.12-slim@sha256:191083cdf6c7bda8c76158983163ead5d5cf7b77cf3033e805bb0f5296f51b4b AS package
WORKDIR /build
COPY backend/ ./
RUN pip wheel --no-deps --wheel-dir /wheels .

FROM python:3.12-slim@sha256:191083cdf6c7bda8c76158983163ead5d5cf7b77cf3033e805bb0f5296f51b4b AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY backend/requirements-cpu.lock ./
RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 libgomp1 && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir --require-hashes -r requirements-cpu.lock && useradd --uid 10001 --create-home gcai
COPY --from=package /wheels /wheels
RUN pip install --no-deps /wheels/*.whl && rm -rf /wheels
COPY backend/gunicorn.conf.py ./gunicorn.conf.py
RUN mkdir -p /var/lib/gcai/artifacts && chown -R 10001:10001 /var/lib/gcai
ENV GCAI_ARTIFACT_DIR=/var/lib/gcai/artifacts
USER 10001:10001
CMD ["gunicorn", "--config", "gunicorn.conf.py", "app.wsgi:application"]

FROM runtime AS test
USER root
COPY backend/requirements-test.lock /tmp/requirements-test.lock
RUN pip install --no-cache-dir --require-hashes -r /tmp/requirements-test.lock
USER 10001:10001

FROM runtime AS production

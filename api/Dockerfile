FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    DATA_DIR=/data

WORKDIR /app
COPY pyproject.toml ./
COPY api ./api
COPY contracts ./contracts
COPY fixtures ./fixtures
COPY infra/migrations ./infra/migrations
RUN python -m pip install . \
    && groupadd --gid 10001 verres \
    && useradd --uid 10001 --gid verres --create-home verres \
    && mkdir /data && chown verres:verres /data

USER verres
HEALTHCHECK --interval=30s --timeout=20s --start-period=180s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=15).close()"
CMD ["python", "-m", "uvicorn", "api.app.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-proxy-headers"]

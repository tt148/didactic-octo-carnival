FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    JOB_TRACKER_PROJECT_DIR=/app \
    JOB_TRACKER_DATA_DIR=/data

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src
COPY config.json app.py collector.py ./

RUN python -m pip install --no-cache-dir . \
    && useradd --create-home --shell /usr/sbin/nologin tracker \
    && mkdir -p /data \
    && chown tracker:tracker /data

USER tracker

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "from urllib.request import urlopen; urlopen('http://127.0.0.1:8501/_stcore/health', timeout=3)"

CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501", "--server.headless=true"]

FROM python:3.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# mssql-python bundles its ODBC layer, but on Linux it still needs these
# runtime libraries for dynamic loading and Kerberos support.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        libgssapi-krb5-2 \
        libkrb5-3 \
        libltdl7 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./requirements.txt
RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements.txt

COPY app ./app
COPY scripts ./scripts
COPY main.py ./main.py

RUN useradd --create-home --uid 10001 dbachum \
    && chown -R dbachum:dbachum /app

USER dbachum

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health/ready', timeout=3).read()" || exit 1

# Keep one API process while the in-process metrics collector is enabled.
# Multiple workers would each start their own collector loop.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]

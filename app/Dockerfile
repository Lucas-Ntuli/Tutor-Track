FROM python:3.12-slim

# ODBC driver required for SQL Server connectivity via pyodbc
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
        gnupg \
        unixodbc-dev \
&& mkdir -p /etc/apt/keyrings \
&& curl -fsSL https://packages.microsoft.com/keys/microsoft.asc \
    | gpg --dearmor -o /etc/apt/keyrings/microsoft.gpg \
&& echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/microsoft.gpg] https://packages.microsoft.com/debian/12/prod bookworm main" \
    > /etc/apt/sources.list.d/microsoft-prod.list \
&& apt-get update \
&& ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 \
&& apt-get clean \
&& rm -rf /var/lib/apt/lists/*

RUN useradd --create-home appuser
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Only used when TESTING=true (local dev / docker-compose) to hold the
# seeded SQLite file - unused in real deployments, which talk to Azure
# SQL instead.
RUN mkdir -p /app/data && chown appuser:appuser /app/data

USER appuser

EXPOSE 8000

# Container-level liveness check, independent of any orchestrator's
# own probe config - useful for plain `docker run` and docker-compose.
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health/live', timeout=2).status == 200 else 1)"

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

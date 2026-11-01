FROM python:3.12-slim

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates curl build-essential && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy repository contents
COPY . .

# Ensure data and reports directories exist
RUN mkdir -p /app/data /app/data/reports /app/data/logs /app/data/cache

# Environment configuration
ENV PYTHONUNBUFFERED=1
ENV MANGA_ROOT=/sg2b/Share2sgb
ENV DATA_DIR=/app/data
ENV REPORTS_DIR=/app/data/reports
ENV LOGS_DIR=/app/data/logs
ENV DATABASE_PATH=/app/data/mangarunner.db
ENV PORT=7070
ENV HOST=0.0.0.0

EXPOSE 7070

CMD ["python", "-m", "mangarunner.main", "server", "--host", "0.0.0.0", "--port", "7070"]


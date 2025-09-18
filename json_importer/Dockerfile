# JSON Importer Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY json_importer/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy importer script and supporting files
COPY json_importer/ .

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV KNRB_DATA_DIR=/data/knrb_data
ENV TIME_TEAM_DATA_DIR=/data/time_team_data

# Create non-root user for security
RUN groupadd -r importer && useradd -r -g importer importer

# Set proper ownership
RUN chown -R importer:importer /app
USER importer

# Default command (can be overridden)
CMD ["python", "json_importer.py", "--help"]

# Time Team Scraper Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY time_team_scraper/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy scraper script and supporting files
COPY time_team_scraper/ .

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV JSON_OUTPUT_DIR=/data/time_team_data

# Create non-root user for security
RUN groupadd -r scraper && useradd -r -g scraper scraper

# Create logs directory and set proper ownership
RUN mkdir -p logs && chown -R scraper:scraper /app && chmod 755 logs
USER scraper

# Default command (can be overridden)
CMD ["python", "time_team_scraper.py"]
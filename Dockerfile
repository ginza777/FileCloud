FROM python:3.12-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    postgresql-client \
    netcat-openbsd \
    build-essential \
    libpq-dev \
    curl \
    default-jre \
    git \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip
RUN pip install --upgrade pip

# Install Python dependencies
COPY requirements/ /app/requirements/
RUN pip install --no-cache-dir -r requirements/production.txt

# Create necessary directories and set permissions
RUN mkdir -p /app/media /app/media/downloads /app/staticfiles /app/logs /app/backups/postgres/daily /app/backups/postgres/weekly /app/backups/postgres/monthly /app/backups/elasticsearch/daily /app/backups/elasticsearch/weekly /app/backups/elasticsearch/monthly /app/backups/redis/daily /app/backups/redis/weekly /app/backups/redis/monthly && \
    chmod -R 755 /app/media /app/staticfiles /app/logs /app/backups

# Copy project files
COPY . .

# YANGI QADAM: Statik fayllarni Image ichiga yig'ish
# Bu kesh muammolarini hal qiladi va Volume kerak emas.
RUN python manage.py collectstatic --no-input

# Expose port
EXPOSE 8000
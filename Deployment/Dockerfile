# Use official Python runtime as base image
FROM python:3.11-slim

# Set working directory in container
WORKDIR /app

# Install system dependencies (needed for yt-dlp)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy your application code
COPY simple_api_caller_async_download.py .

# Set environment variables
ENV PORT=8080
ENV PYTHONUNBUFFERED=1

# Expose port (Cloud Run will set PORT automatically)
EXPOSE 8080

# Use gunicorn for production instead of Flask development server
# Cloud Run expects the app to listen on the PORT environment variable
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 600 simple_api_caller_async_download:app

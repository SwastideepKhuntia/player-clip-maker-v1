FROM python:3.11-slim

# Install system dependencies: FFmpeg, Chromium for Selenium scraping
RUN apt-get update && apt-get install -y \
    ffmpeg \
    chromium \
    chromium-driver \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Ensure data and output directories exist
RUN mkdir -p data/videos data/csv data/music output/clips

ENV PORT=8000
EXPOSE 8000

CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]

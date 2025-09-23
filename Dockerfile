# Use Python 3.11 slim (stable for pip and setuptools)
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Install system dependencies for building wheels
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
        g++ \
        libffi-dev \
        libssl-dev \
        git \
        && rm -rf /var/lib/apt/lists/*

# Copy requirements first for caching
COPY requirements.txt .

# Upgrade pip, setuptools, wheel
RUN pip install --upgrade pip setuptools wheel

# Install project dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the project
COPY app/ ./app/

# Expose port for FastAPI
EXPOSE 8000

# Run the app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

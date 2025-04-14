# Use an official Python runtime as a parent image
# Using Python 3.9 as a baseline, adjust if needed (e.g., 3.10, 3.11)
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /app

# Prevent interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies required for LibreOffice and Poppler
# Using --no-install-recommends to keep the image smaller
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice \
    poppler-utils \
    # Add any other essential system libraries if discovered later
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

# Copy the requirements file into the container first
# This leverages Docker layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container
# This includes all .py files, .html, .css, .js at the root level now
COPY . .

# Make port 8000 available to the world outside this container
EXPOSE 8000

# Define environment variables with defaults (can be overridden at runtime)
# These should match the defaults in config_loader.py / models.py
ENV MAX_WORKERS=5
ENV PROCESS_TIMEOUT=90
# REMOVED fixed prompt ENV variable
ENV TEMP_DIR_BASE=/tmp/everypage_pure
ENV LIBREOFFICE_COMMAND=libreoffice
ENV PDFTOPPM_COMMAND=pdftoppm
ENV PDFINFO_COMMAND=pdfinfo
ENV LOG_LEVEL=INFO
# API_KEY and GEMINI_API_KEY should be set at runtime using -e flags

# Healthcheck (Optional but recommended)
# Note: The default /health endpoint requires authentication.
# A simple curl check will fail unless the endpoint is unsecured or the key is provided.
# Consider adding an unauthenticated endpoint like /ping for basic checks if needed.
# RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*
# HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
#   CMD curl --fail -H "x-api-key: ${API_KEY:-dummy}" http://localhost:8000/health || exit 1

# Run main_api.py using uvicorn when the container launches
# Listen on 0.0.0.0 to accept connections from outside the container
# Updated entry point to main_api:app
CMD ["uvicorn", "main_api:app", "--host", "0.0.0.0", "--port", "8000"]
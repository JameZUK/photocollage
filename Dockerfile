# Dockerfile
# Instructions for building the Python application image.

# Start with a lightweight official Python image.
FROM python:3.9-slim

# Install system dependencies required for pillow-heif
RUN apt-get update && apt-get install -y --no-install-recommends \
    libheif-dev \
    libde265-dev \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory inside the container.
WORKDIR /app

# Copy the requirements file into the container.
COPY requirements.txt .

# Install the Python dependencies.
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application source code into the container.
COPY . .

# Command to run the application when the container starts.
CMD ["python", "main.py"]

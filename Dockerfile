# Dockerfile
# Instructions for building the Python application image using a multi-stage build
# for a smaller and more secure final image.

# --- Stage 1: Builder ---
# This stage installs dependencies and builds the Python virtual environment.
FROM python:3.9-slim as builder

# Install build-time system dependencies required to compile Python packages.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libheif-dev \
    libde265-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Create a virtual environment to isolate dependencies.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

RUN pip install --upgrade pip

# Copy and install Python requirements.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt


# --- Stage 2: Final Image ---
# This stage creates the lean final image for running the application.
FROM python:3.9-slim

# Install only the necessary run-time system dependencies.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libheif1 \
    libde265-0 \
    fonts-dejavu-core \
    fonts-roboto \
    && rm -rf /var/lib/apt/lists/*

# Create a dedicated, non-root user and group to run the application.
RUN adduser --system --group appuser

WORKDIR /app

# Copy the virtual environment from the builder stage.
COPY --from=builder /opt/venv /opt/venv

# Copy the application source code into the container.
COPY . .

# Set the PATH to include the virtual environment's executables.
ENV PATH="/opt/venv/bin:$PATH"

# Change ownership of the app directory to the new user.
RUN chown -R appuser:appuser /app

# Switch to the non-root user.
USER appuser

# Command to run the application when the container starts.
CMD ["python", "main.py"]



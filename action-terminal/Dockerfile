# Use Python 3.11 slim image as base
FROM python:3.11-slim

# Set environment variables
ENV PYTHONFAULTHANDLER=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    POETRY_VERSION=1.7.1 \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=true \
    POETRY_VIRTUALENVS_IN_PROJECT=false \
    POETRY_VIRTUALENVS_PATH=/tmp/.venvs \
    POETRY_HOME="/opt/poetry" \
    WORKDIR=/workspace \
    PATH="/opt/poetry/bin:$PATH"

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN curl -sSL https://install.python-poetry.org | POETRY_HOME=/opt/poetry python - \
    && chmod a+x /opt/poetry/bin/poetry

# Set up workspace directory
WORKDIR /app

# Copy only dependency files first
COPY poetry.lock pyproject.toml ./

# Install dependencies
RUN poetry install --no-root --no-dev

# Copy the rest of the application
COPY . .

# Install the application
RUN poetry install --no-dev

# Create and set permissions for workspace directory
RUN mkdir -p /workspace && chmod 777 /workspace

# Expose the port the app runs on
EXPOSE 5001

# Command to run the application
CMD ["poetry", "run", "watchgod", "action.app.action_server_runner.main"]


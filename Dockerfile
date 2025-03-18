# Dockerfile for the Flask application
FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements.txt and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY app.py gunicorn_config.py seed_db.py ./
# If you have a templates/ or static/ directory, copy them as well:
# COPY templates/ ./templates/
# COPY static/ ./static/

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PORT=5000

# Expose the port the app runs on
EXPOSE 5000

# Create a non-root user and switch to it
RUN useradd -m appuser
USER appuser

# Run the application using Gunicorn
CMD ["gunicorn", "-c", "gunicorn_config.py", "app:app"]

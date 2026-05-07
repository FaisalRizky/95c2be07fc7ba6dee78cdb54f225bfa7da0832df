FROM python:3.10-slim

WORKDIR /app

# Install system dependencies if any (none needed for sqlite)
# COPY requirements.txt first to leverage Docker cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the backend code
COPY . .

# We expect the database to be at /glenigan.sql (3 levels up from config/db.py)
# This will be handled via docker-compose volume or copy

EXPOSE 8000

# Use sh -c so the shell expands $BACKEND_PORT at container start.
# The JSON-array form does NOT expand env vars — shell form required here.
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${BACKEND_PORT:-8000}"]

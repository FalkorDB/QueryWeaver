# Use a single stage build with FalkorDB base image
FROM falkordb/falkordb:latest

ENV PYTHONUNBUFFERED=1 \
    FALKORDB_HOST=localhost \
    FALKORDB_PORT=6379

USER root

# Install Python and pip, netcat for wait loop in start.sh
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install pipenv
RUN python3 -m pip install --no-cache-dir --break-system-packages pipenv

# Copy Pipfile and Pipfile.lock
COPY Pipfile Pipfile.lock ./

# Install Python dependencies from Pipfile
RUN pipenv sync --system --deploy

# Copy application code
COPY . .

# Copy and make start.sh executable
COPY start.sh /start.sh
RUN chmod +x /start.sh

EXPOSE 5000 6379 3000


# Use start.sh as entrypoint
ENTRYPOINT ["/start.sh"]

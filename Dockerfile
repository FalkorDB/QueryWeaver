# Multi-stage build: Start with Python 3.12 base
FROM python:3.12-bookworm AS python-base

# Main stage: Use FalkorDB base and copy Python 3.12
FROM falkordb/falkordb:latest

ENV PYTHONUNBUFFERED=1 \
    FALKORDB_HOST=localhost \
    FALKORDB_PORT=6379

USER root

# Copy Python 3.12 from the python base image
COPY --from=python-base /usr/local /usr/local

# Install netcat for wait loop in start.sh and system build tools needed for
# compiling Python wheels (g++, make, libc-dev)
RUN apt-get update && apt-get install -y --no-install-recommends \
    netcat-openbsd \
    git \
    build-essential \
    curl \
    ca-certificates \
    gnupg \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/local/bin/python3.12 /usr/bin/python3 \
    && ln -sf /usr/local/bin/python3.12 /usr/bin/python

WORKDIR /app

# Install pipenv
RUN python3 -m pip install --no-cache-dir --break-system-packages pipenv

# Copy Pipfile and Pipfile.lock
COPY Pipfile Pipfile.lock ./

# Install Python dependencies from Pipfile
RUN PIP_BREAK_SYSTEM_PACKAGES=1 pipenv sync --system

# Install Node.js (Node 22) so we can build the frontend inside the image.
# Use NodeSource setup script to get a recent Node version on Debian-based images.
# Remove any pre-installed nodejs first to avoid conflicts.
RUN apt-get update \
    && apt-get remove -y nodejs || true \
    && rm -rf /var/lib/apt/lists/* \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get update \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/* \
    && node --version && npm --version

# Copy only frontend package files so Docker can cache npm installs when
# package.json / package-lock.json don't change.
COPY app/package*.json ./app/

# Install frontend dependencies (reproducible install using package-lock)
RUN if [ -f ./app/package-lock.json ]; then \
            npm --prefix ./app ci --no-audit --no-fund; \
        elif [ -f ./app/package.json ]; then \
            npm --prefix ./app install --no-audit --no-fund; \
        else \
            echo "No frontend package.json found, skipping npm install"; \
        fi

COPY ./app ./app

RUN npm --prefix ./app run build

# Copy application code 
COPY . .

# Copy and make start.sh executable
COPY start.sh /start.sh
RUN chmod +x /start.sh


# Add MCP label
LABEL io.modelcontextprotocol.server.name="com.falkordb/QueryWeaver"

EXPOSE 5000 6379 3000

# Use start.sh as entrypoint
ENTRYPOINT ["/start.sh"]

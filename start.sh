#!/bin/bash
set -e


# Set default values if not set
FALKORDB_HOST="${FALKORDB_HOST:-localhost}"
FALKORDB_PORT="${FALKORDB_PORT:-6379}"

# Start FalkorDB Redis server in background
redis-server --loadmodule /var/lib/falkordb/bin/falkordb.so &

# Wait until FalkorDB is ready
echo "Waiting for FalkorDB to start on $FALKORDB_HOST:$FALKORDB_PORT..."

while ! nc -z "$FALKORDB_HOST" "$FALKORDB_PORT"; do
  sleep 0.5
done


echo "FalkorDB is up - launching Flask..."
exec python3 -m flask --app api.index run --host=0.0.0.0 --port=5000
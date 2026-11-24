#!/bin/bash
set -e

# The image bundles FalkorDB so that a bare `docker run falkordb/queryweaver`
# works on its own. Start it only when the app is going to use it: FALKORDB_URL
# unset (api/extensions.py then connects to localhost:6379), or FALKORDB_URL
# naming this container's own loopback (the .env.example default). When
# FALKORDB_URL points at another host the bundled server would sit unused, so it
# is not started. When it is started it has no password, so it listens on
# 127.0.0.1 only and is never reachable from outside the container.
START_BUNDLED_FALKORDB=true
BUNDLED_FALKORDB_PORT=6379

if [ -n "${FALKORDB_URL:-}" ]; then
  url="${FALKORDB_URL,,}"
  case "$url" in
    redis://*|rediss://*)
      # redis[s]://[user:pass@]host[:port][/db]. Docker's --env-file keeps an
      # inline "# comment" as part of the value, so stop at whitespace too.
      hostport="${url#*://}"
      hostport="${hostport%%[/?#[:space:]]*}"
      hostport="${hostport##*@}"
      case "$hostport" in
        \[*) host="${hostport%%]*}"; host="${host#\[}"; rest="${hostport#*]}" ;;
        *)   host="${hostport%%:*}"; rest="${hostport#"$host"}" ;;
      esac
      port="${rest#:}"
      case "$host" in
        ""|localhost|127.0.0.1|::1) BUNDLED_FALKORDB_PORT="${port:-6379}" ;;
        *) START_BUNDLED_FALKORDB=false ;;
      esac
      ;;
    *)
      START_BUNDLED_FALKORDB=false
      ;;
  esac
fi

if [ "$START_BUNDLED_FALKORDB" = "true" ]; then
  redis-server --bind 127.0.0.1 --port "$BUNDLED_FALKORDB_PORT" \
    --loadmodule /var/lib/falkordb/bin/falkordb.so | cat &
  # $! is `cat`, which exits as soon as redis-server does.
  bundled_falkordb_pid=$!

  echo "Waiting for bundled FalkorDB to start on 127.0.0.1:$BUNDLED_FALKORDB_PORT..."
  while ! nc -z 127.0.0.1 "$BUNDLED_FALKORDB_PORT"; do
    if ! kill -0 "$bundled_falkordb_pid" 2>/dev/null; then
      echo "Bundled FalkorDB exited before accepting connections." >&2
      exit 1
    fi
    sleep 0.5
  done
  echo "FalkorDB is up."
else
  echo "FALKORDB_URL points at an external FalkorDB; not starting the bundled one."
fi

# Reload only when FASTAPI_DEBUG is explicitly true (any case), the same test
# api/index.py applies. Unset means production: no reloader.
if [ "${FASTAPI_DEBUG,,}" = "true" ]; then
  RELOAD_FLAG="--reload"
else
  RELOAD_FLAG=""
fi

echo "Launching FastAPI (uvicorn)..."
exec uvicorn api.index:app --host "${HOST:-0.0.0.0}" --port "${PORT:-5000}" $RELOAD_FLAG

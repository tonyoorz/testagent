#!/bin/bash
set -euo pipefail

# Local PostgreSQL for dual-write mode
# Usage:
#   ./deploy/start_postgres.sh up
#   ./deploy/start_postgres.sh down
#   ./deploy/start_postgres.sh logs

CONTAINER_NAME=${PG_CONTAINER_NAME:-aianalysis-pg}
PG_IMAGE=${PG_IMAGE:-postgres:16}
PG_PORT=${PG_PORT:-5432}
PG_USER=${PG_USER:-octane}
PG_PASSWORD=${PG_PASSWORD:-octane_pwd}
PG_DB=${PG_DB:-octane_local}
PG_DATA_DIR=${PG_DATA_DIR:-"$(pwd)/database/postgres_data"}

mkdir -p "$PG_DATA_DIR"

cmd=${1:-up}

if [[ "$cmd" == "up" ]]; then
  docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
  docker run -d \
    --name "$CONTAINER_NAME" \
    -e POSTGRES_USER="$PG_USER" \
    -e POSTGRES_PASSWORD="$PG_PASSWORD" \
    -e POSTGRES_DB="$PG_DB" \
    -p "$PG_PORT":5432 \
    -v "$PG_DATA_DIR":/var/lib/postgresql/data \
    "$PG_IMAGE"

  echo "✅ PostgreSQL started: $CONTAINER_NAME"
  echo "Connection URL: postgresql://$PG_USER:$PG_PASSWORD@localhost:$PG_PORT/$PG_DB"
  exit 0
fi

if [[ "$cmd" == "down" ]]; then
  docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
  echo "✅ PostgreSQL stopped and container removed: $CONTAINER_NAME"
  exit 0
fi

if [[ "$cmd" == "logs" ]]; then
  docker logs -f "$CONTAINER_NAME"
  exit 0
fi

echo "Unknown command: $cmd"
echo "Usage: $0 [up|down|logs]"
exit 1

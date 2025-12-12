#!/bin/bash
set -e

MAX_RETRIES="${DB_MAX_RETRIES:-10}"
SLEEP_SECONDS="${DB_RETRY_SLEEP:-3}"

echo "Running migrations..."
for i in $(seq 1 "$MAX_RETRIES"); do
  if alembic upgrade head; then
    echo "Migrations applied successfully."
    break
  fi
  echo "Alembic attempt $i/$MAX_RETRIES failed, retrying in $SLEEP_SECONDS sec..."
  sleep "$SLEEP_SECONDS"
  if [ "$i" -eq "$MAX_RETRIES" ]; then
    echo "Failed to apply migrations after $MAX_RETRIES attempts."
    exit 1
  fi
done

echo "Starting application..."
exec "$@"


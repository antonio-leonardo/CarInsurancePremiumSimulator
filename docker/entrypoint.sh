#!/bin/sh
set -e

# Run database migrations only when persistence is switched on.
case "$(printf '%s' "${PERSISTENCE_ENABLED:-false}" | tr '[:upper:]' '[:lower:]')" in
  1 | true | yes | on)
    echo "persistence enabled: running 'alembic upgrade head'"
    alembic upgrade head
    ;;
  *)
    echo "persistence disabled: skipping migrations"
    ;;
esac

exec "$@"

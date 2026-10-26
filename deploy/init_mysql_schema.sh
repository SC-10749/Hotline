#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${DODO_ENV_FILE:-$ROOT_DIR/.env}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Environment file not found: $ENV_FILE" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

if [[ "${DODO_ENV_PROFILE:-local}" == "remote" ]]; then
  for config_key in ${!REMOTE_@}; do
    export "${config_key#REMOTE_}=${!config_key}"
  done
fi

: "${DODO_MYSQL_HOST:?DODO_MYSQL_HOST is required}"
: "${DODO_MYSQL_PORT:?DODO_MYSQL_PORT is required}"
: "${DODO_MYSQL_DATABASE:?DODO_MYSQL_DATABASE is required}"
: "${DODO_MYSQL_USER:?DODO_MYSQL_USER is required}"
: "${DODO_MYSQL_PASSWORD:?DODO_MYSQL_PASSWORD is required}"

if ! command -v mysql >/dev/null 2>&1; then
  echo "mysql client not found. Install mysql-community-client or use docker exec." >&2
  exit 1
fi

echo "Initializing schema in MySQL database: $DODO_MYSQL_DATABASE"
# The dump contains one legacy schema-qualified INSERT for database `dodo`.
# Remove that qualifier so the same dump works with the server's `aicc` database.
sed 's/INSERT INTO `dodo`\.`ai_ppt_template`/INSERT INTO `ai_ppt_template`/' \
  "$ROOT_DIR/sql/ai_db.sql" \
  | mysql --protocol=TCP \
      --host="$DODO_MYSQL_HOST" \
      --port="$DODO_MYSQL_PORT" \
      --user="$DODO_MYSQL_USER" \
      --password="$DODO_MYSQL_PASSWORD" \
      "$DODO_MYSQL_DATABASE"

echo "MySQL schema initialized successfully."

#!/usr/bin/env bash
# Upload local pipeline.db to the Fly.io persistent volume.
# Usage: ./scripts/push-db.sh [app-name]
set -euo pipefail

APP="${1:-repuro-suite}"
LOCAL_DB="${PIPELINE_DB_PATH:-pipeline.db}"

if [[ ! -f "$LOCAL_DB" ]]; then
  echo "ERROR: $LOCAL_DB not found. Set PIPELINE_DB_PATH or run from repo root." >&2
  exit 1
fi

echo "Uploading $LOCAL_DB → $APP:/data/pipeline.db …"
flyctl sftp shell --app "$APP" <<EOF
put $LOCAL_DB /data/pipeline.db
EOF
echo "Done."

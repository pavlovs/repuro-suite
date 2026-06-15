#!/usr/bin/env bash
# Download pipeline.db from Fly.io to local.
# Usage: ./scripts/pull-db.sh [app-name] [local-dest]
set -euo pipefail

APP="${1:-repuro-suite}"
DEST="${2:-pipeline.db}"

echo "Downloading $APP:/data/pipeline.db → $DEST …"
flyctl sftp get --app "$APP" /data/pipeline.db "$DEST"
echo "Done. Local copy at: $DEST"

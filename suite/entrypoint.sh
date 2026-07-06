#!/bin/sh
set -e

# Inject COCKPIT_BASE_PATH into static HTML files so JS knows the prefix
# and rewrite absolute /static/ refs so they route through Caddy correctly
if [ -n "$COCKPIT_BASE_PATH" ]; then
    for f in /app/cockpit/static/index.html; do
        [ -f "$f" ] || continue
        sed -i "s|window\.COCKPIT_BASE=''|window.COCKPIT_BASE='${COCKPIT_BASE_PATH}'|g" "$f"
        sed -i "s|href=\"/static/|href=\"${COCKPIT_BASE_PATH}/static/|g" "$f"
        sed -i "s|src=\"/static/|src=\"${COCKPIT_BASE_PATH}/static/|g" "$f"
    done
fi

# Ensure /data (Fly volume) and app-local data dirs are writable by appuser
mkdir -p /data /app/allex/data/output /app/dealroom/data
chown -R appuser:appuser /data /app/allex/data /app/dealroom/data

# If Litestream replica URL is configured, restore-on-empty then wrap supervisord
# for continuous backup. WITHOUT the restore step, a fresh/replaced Fly volume
# boots with EMPTY DBs, and `litestream replicate` would then push those empties
# to S3, destroying the only off-volume backup. Restore only when the local file
# is absent; -if-replica-exists makes the very first boot (no backup yet) a no-op.
if [ -n "$LITESTREAM_REPLICA_URL" ]; then
    for dbname in pipeline dealroom cockpit investor; do
        if [ ! -f "/data/${dbname}.db" ]; then
            echo "litestream: /data/${dbname}.db missing — attempting restore"
            litestream restore -if-replica-exists -config /etc/litestream.yml \
                "/data/${dbname}.db" || echo "litestream: no replica for ${dbname}.db (fresh)"
        fi
    done
    chown -R appuser:appuser /data
    exec litestream replicate -config /etc/litestream.yml -exec "supervisord -c /etc/supervisor/supervisord.conf"
else
    exec supervisord -c /etc/supervisor/supervisord.conf
fi

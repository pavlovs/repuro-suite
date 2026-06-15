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

# If Litestream replica URL is configured, wrap supervisord for continuous backup
if [ -n "$LITESTREAM_REPLICA_URL" ]; then
    exec litestream replicate -config /etc/litestream.yml -exec "supervisord -c /etc/supervisor/supervisord.conf"
else
    exec supervisord -c /etc/supervisor/supervisord.conf
fi

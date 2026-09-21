#!/usr/bin/env bash
# Push the BA9 Excel-state payload to the Fly prod pipeline.db and apply it (dry-run first, then --apply).
# Requires: flyctl auth login done on this machine. Run from Git Bash:
#   bash scripts/push_excel_state_to_fly.sh data/exports/260917_ba9_excel_state.json
# Mechanism: files are shipped as base64 in <=20 KB chunks via `flyctl ssh console -C` (no sftp, no proxy needed),
# prod DB is backed up on the volume before the apply.
set -euo pipefail
APP=repuro-suite
PAYLOAD="${1:?payload json path}"
TAG="${2:-pre-sync}"   # backup name suffix, e.g. pre-ba9sync
HERE="$(cd "$(dirname "$0")" && pwd)"
STAMP="$(date +%Y-%m-%d)-$TAG"

fssh() { flyctl ssh console -a "$APP" -C "$1" 2>&1 | grep -v "handle is invalid" || true; }

ship() {  # ship <local file> <remote path>
  local src="$1" dst="$2" b64
  b64=$(base64 -w0 "$src")
  fssh "sh -c 'rm -f $dst.b64'"
  local i=0 len=${#b64} chunk=20000
  while [ $i -lt $len ]; do
    fssh "sh -c 'printf %s ${b64:$i:$chunk} >> $dst.b64'" >/dev/null
    i=$((i + chunk))
  done
  fssh "sh -c 'base64 -d $dst.b64 > $dst && rm $dst.b64 && wc -c $dst'"
}

echo "== whoami"; flyctl auth whoami 2>&1 | grep -v "handle is invalid"
echo "== ship script + payload"
ship "$HERE/apply_excel_state.py" /tmp/apply_excel_state.py
ship "$PAYLOAD" /tmp/payload.json
echo "== backup prod db"
fssh "sh -c 'cp /data/pipeline.db /data/pipeline-backup-$STAMP.db && ls -la /data/pipeline-backup-$STAMP.db'"
echo "== dry-run"
fssh "python3 /tmp/apply_excel_state.py /data/pipeline.db /tmp/payload.json"
echo "== apply"
fssh "python3 /tmp/apply_excel_state.py /data/pipeline.db /tmp/payload.json --apply"
echo "== verify (expect 0 changes)"
fssh "python3 /tmp/apply_excel_state.py /data/pipeline.db /tmp/payload.json"
fssh "python3 -c \"import sqlite3;c=sqlite3.connect('/data/pipeline.db');print('rows',c.execute('select count(*) from company_records').fetchone(),'BA9',c.execute(\\\"select count(*) from company_records where briefaktion='BA9'\\\").fetchone(),'keller',c.execute(\\\"select domain,full_name from company_records where domain like 'keller-med%'\\\").fetchall(),'integrity',c.execute('pragma integrity_check').fetchone())\""

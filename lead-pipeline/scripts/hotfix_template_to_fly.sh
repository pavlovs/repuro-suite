#!/usr/bin/env bash
# Hot-patch the ALLEX dashboard template on the Fly prod machine (the server re-reads it on every request).
# Scope: ONE file, /app/allex/src/pipeline/templates/dashboard_v2.html. No deploy, no other app touched.
# The container filesystem is ephemeral: a machine restart or the next `flyctl deploy` replaces it, so the
# same change MUST also be committed on dev so the next real deploy carries it.
# Usage (Git Bash): bash scripts/hotfix_template_to_fly.sh [expected_prod_blob_sha1_prefix] [relative file] [marker]
#   default file = src/pipeline/templates/dashboard_v2.html; any other file under lead-pipeline/ works the same way
#   (e.g. src/pipeline/dashboard.py). The marker is grepped in the startup HTML after the restart.
set -euo pipefail
APP=repuro-suite
HERE="$(cd "$(dirname "$0")" && pwd)"
REL="${2:-src/pipeline/templates/dashboard_v2.html}"
SRC="$HERE/../$REL"
DST="/app/allex/$REL"
MARKER="${3:-leadsFilterPopHtml}"
STAMP=$(date +%Y-%m-%d-%H%M)
EXPECT="${1:-}"

fssh() { flyctl ssh console -a "$APP" -C "$1" 2>&1 | grep -v "handle is invalid" || true; }

local_sha=$(git -C "$HERE/.." hash-object "$SRC" | cut -c1-10)
echo "== local template blob: $local_sha ($(wc -c < "$SRC") bytes)"

echo "== prod before"
fssh "python3 -c \"import hashlib;d=open('$DST','rb').read();print('prod blob',hashlib.sha1(b'blob %d\\\\0'%len(d)+d).hexdigest()[:10],len(d))\"" | tee /tmp/hotfix_before.txt
if [ -n "$EXPECT" ] && ! grep -q "prod blob $EXPECT" /tmp/hotfix_before.txt; then
  echo "ABORT: prod template is not the expected blob $EXPECT"; exit 1
fi

echo "== backup on machine"
fssh "sh -c 'cp $DST $DST.bak-$STAMP && ls -la $DST.bak-$STAMP'"

echo "== ship (base64 chunks)"
b64=$(base64 -w0 "$SRC")
fssh "sh -c 'rm -f $DST.b64'" >/dev/null
i=0; len=${#b64}; chunk=20000
while [ $i -lt $len ]; do
  fssh "sh -c 'printf %s ${b64:$i:$chunk} >> $DST.b64'" >/dev/null
  i=$((i + chunk))
done
fssh "sh -c 'base64 -d $DST.b64 > $DST.new && rm $DST.b64 && mv $DST.new $DST'"

echo "== prod after (expect $local_sha)"
fssh "python3 -c \"import hashlib;d=open('$DST','rb').read();print('prod blob',hashlib.sha1(b'blob %d\\\\0'%len(d)+d).hexdigest()[:10],len(d))\""
# The prod server caches the HTML at startup: restart the process so it re-reads the template (supervisord respawns it).
# NEVER fetch the served page inside the container to check: the ~8 MB response on the 512 MB machine OOM-killed the
# process on 2026-09-22 08:44 UTC (5th kill that day). Check the HTML the new process writes at startup instead.
echo "== restart allex process (supervisord respawns it)"
fssh "python3 -c \"import os,signal;me=str(os.getpid());cl=lambda p:open('/proc/'+p+'/cmdline','rb').read();hit=[p for p in os.listdir('/proc') if p.isdigit() and p!=me and cl(p).startswith(b'python') and b'/app/allex/pipeline.py' in cl(p) and b'dashboard' in cl(p)];[os.kill(int(p),signal.SIGTERM) for p in hit];print('SIGTERM sent to allex pid(s)',hit)\""
sleep 12
echo "== startup HTML check (expect a fresh timestamp and marker>0)"
fssh "sh -c 'f=/app/allex/data/output/dashboard_\$(date +%Y%m%d).html; ls -la --time-style=+%H:%M:%S \$f; echo markers \$(grep -c $MARKER \$f)'"

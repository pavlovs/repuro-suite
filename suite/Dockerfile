FROM python:3.12-slim AS base

# Install Caddy
COPY --from=caddy:2-alpine /usr/bin/caddy /usr/bin/caddy

# Install Litestream (continuous SQLite replication)
ADD https://github.com/benbjohnson/litestream/releases/download/v0.3.13/litestream-v0.3.13-linux-amd64.tar.gz /tmp/litestream.tar.gz
RUN tar -xzf /tmp/litestream.tar.gz -C /usr/local/bin/ litestream && rm /tmp/litestream.tar.gz

# Install supervisor
RUN pip install --no-cache-dir supervisor

WORKDIR /app

# --- ALLEX dependencies (prod only — no pytest, anthropic, tqdm, bs4, lxml, httpx) ---
COPY lead-pipeline/requirements-prod.txt /app/allex/requirements.txt
RUN pip install --no-cache-dir -r /app/allex/requirements.txt

# --- COCKPIT dependencies (prod only — no pytest, openpyxl) ---
COPY cockpit/requirements-prod.txt /app/cockpit/requirements.txt
RUN pip install --no-cache-dir -r /app/cockpit/requirements.txt

# --- DEALROOM dependencies ---
COPY dealroom/requirements-prod.txt /app/dealroom/requirements.txt
RUN pip install --no-cache-dir -r /app/dealroom/requirements.txt

# --- INVESTOR ROOM dependencies ---
COPY boardroom/requirements-prod.txt /app/boardroom/requirements.txt
RUN pip install --no-cache-dir -r /app/boardroom/requirements.txt

# Non-root user — supervisord runs as root, child processes as appuser
RUN adduser --disabled-password --gecos "" --no-create-home appuser

# --- Copy application code ---
COPY lead-pipeline/ /app/allex/
COPY dealroom/ /app/dealroom/
COPY cockpit/ /app/cockpit/
COPY boardroom/ /app/boardroom/
COPY suite/static/ /app/suite/static/

# --- Config files ---
COPY suite/Caddyfile /etc/caddy/Caddyfile
COPY suite/supervisord.conf /etc/supervisor/supervisord.conf
COPY suite/litestream.yml /etc/litestream.yml
COPY suite/entrypoint.sh /app/entrypoint.sh
RUN sed -i 's/\r$//' /app/entrypoint.sh /etc/caddy/Caddyfile /etc/supervisor/supervisord.conf && chmod +x /app/entrypoint.sh

# Clean up .venv dirs (not needed in container)
RUN rm -rf /app/allex/.venv /app/dealroom/.venv /app/cockpit/.venv /app/boardroom/.venv

EXPOSE 8080

CMD ["/app/entrypoint.sh"]

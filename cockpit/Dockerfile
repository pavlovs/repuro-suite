FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src/ src/
COPY static/ static/
COPY scripts/ scripts/
COPY cockpit.py .
# SQLite on the Fly volume; dealroom sync is push-based on Fly (COCKPIT_DEALROOM_DB unset
# -> sync degrades gracefully, mirror updated via /cockpit-push from local machines)
ENV COCKPIT_DB=/data/cockpit.db COCKPIT_SYNC_INTERVAL=0 COCKPIT_PORT=8080
EXPOSE 8080
CMD ["python", "cockpit.py", "serve", "--port", "8080"]

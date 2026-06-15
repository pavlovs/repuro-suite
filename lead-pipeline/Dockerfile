FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# DB lives on a Fly persistent volume; set path via env
ENV PIPELINE_DB_PATH=/data/pipeline.db

EXPOSE 8080

CMD ["python", "pipeline.py", "dashboard", "--serve", "--port", "8080"]

# 1. Base Image: official lightweight Python runtime
FROM python:3.12-slim

# Node.js for the ingestion package. packages/ingestion has no npm
# dependencies, so the node binary alone is enough.
COPY --from=node:22-slim /usr/local/bin/node /usr/local/bin/node

# 2. Working Directory: set the internal container directory
WORKDIR /app

# 3. Dependencies: copy the dependency manifest first to leverage layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. Application Code & Startup Command
COPY . .
# The database and collected feedback live in /app/state; mount a volume there
# to keep them across container restarts. The scheduler runs the nightly
# collection cycle at 02:00 Ottawa time (TR8).
RUN mkdir -p /app/state
ENV TZ=America/Toronto \
    TRFD_SCHEDULER=1 \
    TRFD_DB=/app/state/trfd.db \
    TRFD_REVIEWS_FILE=/app/state/reviews.jsonl
EXPOSE 5000
CMD ["python", "app.py"]

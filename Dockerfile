# 1. Base Image: official lightweight Python runtime
FROM python:3.12-slim

# 2. Working Directory: set the internal container directory
WORKDIR /app

# 3. Dependencies: copy the dependency manifest first to leverage layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. Application Code & Startup Command
COPY . .
EXPOSE 5000
CMD ["python", "app.py"]

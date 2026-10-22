# Build from this directory:  docker build -t fnx-auth-api services/auth_api
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY auth/ ./auth/
CMD ["uvicorn", "auth.main:app", "--host", "0.0.0.0", "--port", "8000"]

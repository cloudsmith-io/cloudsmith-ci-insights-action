FROM python:3.12-slim

WORKDIR /app

COPY package_insights.py ./
COPY config.py ./
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

ENTRYPOINT ["python", "/app/package_insights.py"]

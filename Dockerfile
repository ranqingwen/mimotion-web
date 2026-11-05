FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY core ./core
COPY runner.py app.py ./
COPY templates ./templates

ENV TZ=Asia/Shanghai \
    DATA_DIR=/app/data \
    PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["waitress-serve", "--host=0.0.0.0", "--port=8000", "app:server"]

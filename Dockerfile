FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# 任意: ローカル Docker 実行時に分かりやすく
EXPOSE 8080

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Cloud Run は $PORT を注入するので、自分で ENV PORT を固定しない
CMD ["/entrypoint.sh"]

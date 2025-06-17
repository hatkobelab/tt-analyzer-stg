FROM python:3.11-slim

WORKDIR /app

# 依存をインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリ一式をコピー
COPY . .

EXPOSE 8080
ENV PORT 8080

# entrypoint で secrets.toml を生成して起動
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
CMD ["/entrypoint.sh"]

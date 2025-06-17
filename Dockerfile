# ベースイメージ
FROM python:3.11-slim

# 作業ディレクトリ
WORKDIR /app

# 依存インストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションコードをコピー
COPY . .

# Cloud Run が LISTEN するポートを明示
ENV PORT 8080
EXPOSE 8080

# 起動コマンド
CMD ["streamlit", "run", "table_tennis_analyzer.py", \
     "--server.port", "8080", \
     "--server.address", "0.0.0.0", \
     "--server.headless", "true"]

FROM python:3.11-slim
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 🔽 ここが追加ポイント
# build-arg から受け取った TOML をイメージ内へコピー
ARG TOML_FILE
COPY ${TOML_FILE} /app/.streamlit/secrets.toml

COPY . .
EXPOSE 8080
CMD ["streamlit", "run", "table_tennis_analyzer.py",
     "--server.port", "8080",
     "--server.address", "0.0.0.0",
     "--server.headless", "true"]

#!/bin/bash
set -e

# Streamlit が探す .streamlit/secrets.toml を生成
mkdir -p /app/.streamlit
echo "$STREAMLIT_SECRETS_TOML" > /app/.streamlit/secrets.toml

# アプリ起動
exec streamlit run table_tennis_analyzer.py \
     --server.port "${PORT:-8080}" \
     --server.address "0.0.0.0" \
     --server.headless true

#!/bin/bash

# 変数 STREAMLIT_SECRETS の \n を実際の改行に展開して書き込む
mkdir -p /app/.streamlit
printf '%b' "$STREAMLIT_SECRETS" > /app/.streamlit/secrets.toml

# Streamlit アプリを起動
streamlit run table_tennis_analyzer.py \
  --server.port 8080 \
  --server.address 0.0.0.0 \
  --server.headless true

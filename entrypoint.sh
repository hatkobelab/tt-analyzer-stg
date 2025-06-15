#!/bin/bash

# 環境変数から secrets.toml を生成
mkdir -p /app/.streamlit
echo "$STREAMLIT_SECRETS" > /app/.streamlit/secrets.toml

# Streamlit を起動
streamlit run table_tennis_analyzer.py \
    --server.port 8080 \
    --server.address 0.0.0.0 \
    --server.headless true

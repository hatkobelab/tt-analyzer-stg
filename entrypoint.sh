#!/bin/bash
mkdir -p /app/.streamlit
cp /etc/secrets/streamlit-secrets /app/.streamlit/secrets.toml

exec streamlit run table_tennis_analyzer.py \
  --server.port 8080 \
  --server.address 0.0.0.0 \
  --server.headless true

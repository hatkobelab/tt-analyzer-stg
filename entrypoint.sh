#!/bin/bash
echo "=== DEBUG ==="
ls -al /etc/secrets || true
ls -al /app/.streamlit || true
echo "=== /DEBUG ==="

mkdir -p /app/.streamlit
cp /etc/secrets/streamlit-secrets /app/.streamlit/secrets.toml || true

exec streamlit run table_tennis_analyzer.py \
     --server.port 8080 \
     --server.address 0.0.0.0 \
     --server.headless true

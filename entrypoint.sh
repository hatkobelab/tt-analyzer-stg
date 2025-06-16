#!/bin/bash
echo "=== DEBUG: /etc/secrets ==="
ls -al /etc/secrets
cat /etc/secrets/streamlit-secrets || echo "No streamlit-secrets file"
echo "=== /app/.streamlit ==="
mkdir -p /app/.streamlit
cp /etc/secrets/streamlit-secrets /app/.streamlit/secrets.toml
ls -al /app/.streamlit
cat /app/.streamlit/secrets.toml || echo "No secrets.toml file"
echo "=== END DEBUG ==="

exec streamlit run table_tennis_analyzer.py \
  --server.port 8080 \
  --server.address 0.0.0.0 \
  --server.headless true

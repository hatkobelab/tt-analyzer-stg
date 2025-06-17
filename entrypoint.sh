#!/bin/bash
set -e

mkdir -p /app/.streamlit

# Secretが安定してコピーできるまでリトライ
for i in {1..10}; do
  cp /etc/secrets/streamlit-secrets /app/.streamlit/secrets.toml 2>/dev/null && break
  echo "[WARN] Secret file not ready yet, retrying ($i/10)..."
  sleep 0.5
done

# コピーできてなければ fatal
if [ ! -f /app/.streamlit/secrets.toml ]; then
  echo "[FATAL] Secret file copy failed, exiting"
  ls -al /etc/secrets
  exit 1
fi

exec streamlit run table_tennis_analyzer.py \
     --server.port "${PORT:-8080}" \
     --server.address 0.0.0.0 \
     --server.headless true

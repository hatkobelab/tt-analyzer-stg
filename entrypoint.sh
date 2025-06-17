#!/bin/bash
set -e
echo "== DEBUG: config & secrets =="
cat /app/.streamlit/config.toml || echo "config.toml not found"
ls -l /etc/secrets || true
echo "== /DEBUG =="

exec streamlit run table_tennis_analyzer.py \
     --logger.level debug \
     --server.port "${PORT:-8080}" \
     --server.address 0.0.0.0 \
     --server.headless true

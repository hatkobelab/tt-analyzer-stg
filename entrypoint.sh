#!/bin/bash
# デバッグ用: きちんとファイルがあるか確認
echo "=== DEBUG /etc/secrets ==="
ls -l /etc/secrets || true
echo "=== DEBUG /app/.streamlit ==="
ls -l /app/.streamlit || true
echo "=== END DEBUG ==="

exec streamlit run table_tennis_analyzer.py \
     --server.port ${PORT:-8080} \
     --server.address 0.0.0.0 \
     --server.headless true

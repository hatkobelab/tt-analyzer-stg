#!/bin/bash
# もはや /app/.streamlit へのコピーは不要
exec streamlit run table_tennis_analyzer.py \
     --server.port "${PORT:-8080}" \
     --server.address 0.0.0.0 \
     --server.headless true

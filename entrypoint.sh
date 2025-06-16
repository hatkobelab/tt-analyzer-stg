#!/bin/bash
mkdir -p /app/.streamlit

# Cloud Run の Secret ボリュームが /etc/secrets/streamlit-secrets にある前提
cp /etc/secrets/streamlit-secrets /app/.streamlit/secrets.toml

exec streamlit run table_tennis_analyzer.py \
     --server.port ${PORT:-8080} \
     --server.address 0.0.0.0 \
     --server.headless true

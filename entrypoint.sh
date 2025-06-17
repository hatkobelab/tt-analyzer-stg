# entrypoint.sh は単純起動だけに
#!/bin/bash
exec streamlit run table_tennis_analyzer.py \
     --server.port "${PORT:-8080}" \
     --server.address 0.0.0.0 \
     --server.headless true

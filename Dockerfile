FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
ENV PORT 8080
ENV STREAMLIT_SECRETS_PATH="/app/.streamlit/secrets.toml"
CMD ["streamlit", "run", "table_tennis_analyzer.py",
     "--server.port", "8080",
     "--server.address", "0.0.0.0",
     "--server.headless", "true"]

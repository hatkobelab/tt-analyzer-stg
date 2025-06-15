FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

ENV PORT 8080
ENV STREAMLIT_SECRETS_PATH="/app/.streamlit/secrets.toml"

# スクリプトを起動エントリポイントとして使う
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

CMD ["/entrypoint.sh"]

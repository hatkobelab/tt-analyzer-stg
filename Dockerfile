FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt ./
COPY . ./

RUN pip install --upgrade pip && \
    pip install -r requirements.txt

ENV STREAMLIT_SERVER_HEADLESS=true
ENV STREAMLIT_SERVER_ENABLECORS=false

EXPOSE 8080

CMD ["streamlit", "run", "table_tennis_analyzer.py", "--server.port", "8080"]

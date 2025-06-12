FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt ./
COPY . ./

RUN pip install --upgrade pip && \
    pip install -r requirements.txt

ENV PORT=8501
ENV STREAMLIT_SERVER_HEADLESS=true
ENV STREAMLIT_SERVER_PORT=8501
ENV STREAMLIT_SERVER_ENABLECORS=false

EXPOSE 8501

CMD ["streamlit", "run", "table_tennis_analyzer.py"]

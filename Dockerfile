FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY requirements.txt .
COPY requirements-embeddings.txt .
RUN pip install --no-cache-dir -r requirements.txt
ARG INSTALL_EMBEDDINGS=false
RUN if [ "$INSTALL_EMBEDDINGS" = "true" ]; then pip install --no-cache-dir -r requirements-embeddings.txt; fi
COPY app.py README.md ./
COPY harmonizer ./harmonizer
COPY data ./data

EXPOSE 8501 8000
CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501"]

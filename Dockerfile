FROM python:3.10-slim

WORKDIR /app

# Dépendances système pour psycopg2-binary et autres libs C
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Installe les dépendances Python en premier (cache Docker)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copie le reste du code
COPY . .

# Streamlit
EXPOSE 8501

CMD ["streamlit", "run", "streamlit_app/app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true"]
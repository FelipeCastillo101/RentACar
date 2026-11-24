FROM python:3.12-slim

WORKDIR /app

# Dependencias del sistema para compilar psycopg2 y manejar imágenes
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt


COPY . .

# Dar permisos de ejecución al entrypoint
RUN chmod +x entrypoint.sh

EXPOSE 8000

CMD ["./entrypoint.sh"]
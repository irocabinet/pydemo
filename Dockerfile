# Build și rulare fără internet: imaginea conține toate resursele (CSS/JS/fonturi).
# Construiește pe o mașină cu internet, apoi transferă imaginea (docker save/load) pe serverul offline.

FROM python:3.11-slim

WORKDIR /app

# curl pentru scriptul de descărcare resurse offline
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Copiază cerințe și instalează dependențele
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiază aplicația
COPY . .

# Descarcă toate resursele frontend în static/vendor (necesită internet la build)
RUN chmod +x scripts/download_vendor_assets.sh && ./scripts/download_vendor_assets.sh

# Resursele sunt în imagine; la rulare nu e nevoie de internet
ENV USE_LOCAL_VENDOR=1

EXPOSE 5000

# Gunicorn pentru producție
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "app:app"]

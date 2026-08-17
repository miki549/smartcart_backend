#!/bin/bash

# Kilépés, ha bármelyik parancs hibát dobna
set -e

echo "1. Friss kód letöltése a GitHubról..."
git pull

echo "2. Új SmartCart Docker image felépítése..."
docker build -t smartcart-backend .

echo "3. Régi SmartCart konténer leállítása..."
docker rm -f smartcart-app 2>/dev/null || true

# Szükséges mappák és SQLite db fájl biztosítása a gazdagépen kötetcsatoláshoz
mkdir -p uploads
touch smartcart.db

docker run -d \
  -p 8000:8000 \
  --name smartcart-app \
  --restart unless-stopped \
  --env-file .env \
  -v $(pwd)/uploads:/app/uploads \
  -v $(pwd)/smartcart.db:/app/smartcart.db \
  smartcart-backend

echo "Kész! A SmartCart szerver sikeresen frissítve lett és fut a 8000-es porton."
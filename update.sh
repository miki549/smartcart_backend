#!/bin/bash

set -e

echo "1. Friss kód letöltése a GitHubról..."
git pull

echo "2. Régi konténerek leállítása..."
docker compose down || true

echo "3. Új konténerek felépítése és indítása..."
mkdir -p uploads
docker compose up -d --build

echo "Kész! A PostgreSQL adatbázis és a SmartCart backend fut a háttérben."
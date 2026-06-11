#!/usr/bin/env bash
# ChroniCare — script de build Render
set -o errexit

echo "── 1/3 Installation des dépendances ──────────────────────────"
pip install --upgrade pip
pip install -r requirements.txt

echo "── 2/3 Collecte des fichiers statiques ───────────────────────"
python manage.py collectstatic --no-input --clear

echo "── 3/3 Application des migrations ────────────────────────────"
python manage.py migrate --no-input

echo "✓ Build terminé avec succès"

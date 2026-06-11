#!/usr/bin/env bash
# ChroniCare — script de build Render
# Le build NE doit PAS toucher la DB (elle n'est pas garantie disponible
# pendant cette phase). Les migrations se font au démarrage (startCommand).
set -o errexit

echo "── 1/2 Installation des dépendances ──────────────────────────"
pip install --upgrade pip
pip install -r requirements.txt

echo "── 2/2 Collecte des fichiers statiques ───────────────────────"
python manage.py collectstatic --no-input --clear

echo "✓ Build terminé avec succès"

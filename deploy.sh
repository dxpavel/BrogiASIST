#!/bin/bash
# BrogiASIST PROD deploy script — určeno pro VM 103 (10.55.2.231)
#
# Co dělá:
#   1. git pull origin main            ← stáhne změny z GitHub
#   2. docker compose build           ← rebuild image scheduleru a dashboardu
#   3. docker compose up -d           ← restart kontejnerů s novou image
#   4. docker compose ps              ← výpis stavu
#
# Lokální data (mimo git) zůstávají nedotčené:
#   .env, ollama_data/, attachments/, logs/, postgres_data (volume), chroma_data (volume)
#
# Použití: cd /home/pavel/brogiasist && ./deploy.sh

set -e
cd "$(dirname "$0")"

echo "════════════════════════════════════════"
echo "  BrogiASIST PROD deploy — $(date '+%Y-%m-%d %H:%M:%S')"
echo "════════════════════════════════════════"

echo ""
echo "▶ git pull origin main"
git pull origin main

echo ""
echo "▶ docker compose build (scheduler + dashboard)"
docker compose build scheduler dashboard

echo ""
echo "▶ docker compose up -d (recreate s novou image)"
docker compose up -d

echo ""
echo "▶ stav kontejnerů:"
docker compose ps

echo ""
echo "✅ deploy hotový — $(date '+%H:%M:%S')"

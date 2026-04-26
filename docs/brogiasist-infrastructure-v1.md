---
Název: Infrastruktura BrogiASIST
Soubor: docs/brogiasist-infrastructure-v1.md
Verze: 3.0
Poslední aktualizace: 2026-04-26
Popis: Fyzické stroje, sítě, DEV stack (reálný), PROD stack (plánovaný), rozdíly
Změněno v: 3.0 — kompletní přepis, jasné oddělení DEV vs PROD
---

# Infrastruktura — BrogiASIST

---

## Fyzické stroje

| Stroj | Hostname | IP (LAN) | OS | Role |
|---|---|---|---|---|
| MacBook Pro | Paja-MacBook-Pro | 10.55.2.73 | macOS | **DEV** — vývoj, Claude Desktop |
| Mac Studio | PajaAppleStudio | 10.55.2.117 | macOS 26.3 | **PROD Apple Bridge** — OmniFocus, Notes, Reminders, Files |
| BrogiServer | os01.dxpsolutions.cz | veřejná IP (Forpsi VPS) | Linux RHEL9 | **PROD server** — Docker stack, DB, AI, scheduler |
| Synology NAS | — | LAN | DSM | Sdílené úložiště, zálohy (SynologyDrive) |

## Sítě

| Síť | Rozsah | Kdo vidí koho |
|---|---|---|
| LAN domácí | 10.55.2.0/24 | MacBook ↔ Apple Studio ↔ Synology |
| Internet | veřejná IP | BrogiServer dostupný přes SSH (Forpsi) |
| LAN → BrogiServer | přes internet | MacBook se připojuje přes SSH klíč |

## SSH přístupy

```bash
# BrogiServer (Linux root)
ssh forpsi-root
# = ssh root@os01.dxpsolutions.cz -i ~/.ssh/brogibr_ed25519

# Apple Studio (macOS)
ssh dxpavel@10.55.2.117
```

---

## DEV — reálný stav (MacBook Pro)

### Docker Compose stack

Projekt: `/Users/pavel/SynologyDrive/001 DXP/009 BrogiASIST/`
Spuštění: `docker compose up -d`

| Kontejner | Image | Port host:container | Účel |
|---|---|---|---|
| `brogi_postgres` | postgres:16 | **5433**:5432 | PostgreSQL (5433 kvůli konfliktu s lokálním PG) |
| `brogi_chromadb` | chromadb/chroma | 8000:8000 | ChromaDB — action learning |
| `brogi_dashboard` | FastAPI build | 9000:9000 | WebUI dashboard |
| `brogi_scheduler` | FastAPI build | 9001:9001 | IMAP IDLE + scheduler + TG callback |

### Služby mimo Docker (na MacBook hostu)

| Služba | Port | Autostart | URL z kontejnerů |
|---|---|---|---|
| Apple Bridge (FastAPI) | 9100 | launchd `cz.brogiasist.apple-bridge` | `http://host.docker.internal:9100` |
| Ollama + Llama3.2-vision:11b | 11434 | manuálně / launchd | `http://host.docker.internal:11434` |
| Ollama model nomic-embed-text | — | součást Ollama | totéž |

### Sdílené složky (bind mounts)

| Host cesta | Container cesta | Účel |
|---|---|---|
| `/Users/pavel/Desktop/OmniFocus` | `/app/attachments` | Přílohy emailů (DEV only) |
| `./logs` | `/app/logs` | Logy scheduleru |

### Klíčové ENV hodnoty (DEV)

```env
APPLE_BRIDGE_URL=http://host.docker.internal:9100
OLLAMA_URL=http://host.docker.internal:11434
CHROMA_HOST=chromadb
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
```

### Git

| Větev | Účel |
|---|---|
| `main` | stabilní základ |
| `0.0.1` | první verze |
| `0.1.0` | aktuální DEV (klasifikace, Chroma WebUI, Claude spam, kontakty) |
| `1` | vývoj příloh base64 + PROD příprava |

---

## PROD — plánovaný stav

### Architektura

```
BrogiServer (os01.dxpsolutions.cz)        PajaAppleStudio (10.55.2.117)
══════════════════════════════════         ══════════════════════════════
Docker Compose stack:                       Apple Bridge (FastAPI, launchd)
  PostgreSQL                                  → OmniFocus
  ChromaDB                                    → Apple Notes
  Dashboard (WebUI)                           → Apple Reminders
  Scheduler (IMAP, TG, classify)              → ~/Desktop/BrogiAssist/ (přílohy)
Ollama (system service):
  llama3.2-vision:11b
  nomic-embed-text
```

### BrogiServer — Docker Compose (PROD)

| Kontejner | Port host:container | Poznámka |
|---|---|---|
| `postgres` | **5432**:5432 | standardní port (žádný konflikt) |
| `chromadb` | 8000:8000 | stejné jako DEV |
| `dashboard` | 9000:9000 | za nginx proxy |
| `scheduler` | 9001:9001 | interní |

### BrogiServer — mimo Docker

| Služba | Port | Způsob spuštění |
|---|---|---|
| Ollama | 11434 | systemd service (`systemctl start ollama`) |

### PajaAppleStudio — Apple Bridge (PROD)

| Parametr | Hodnota |
|---|---|
| Umístění | `~/brogiasist-bridge/` |
| Port | 9100 |
| Autostart | launchd `cz.brogiasist.apple-bridge` |
| Python | 3.9.6 (⚠️ nutná kompatibilita — bez `str\|None` syntax) |
| Přílohy složka | `~/Desktop/BrogiAssist/` |
| Full Disk Access | nutný pro Terminal/Python (Calendar, Contacts) |

### Klíčové ENV hodnoty (PROD — rozdíly od DEV)

```env
APPLE_BRIDGE_URL=http://10.55.2.117:9100      # ← Apple Studio IP (ne host.docker.internal)
OLLAMA_URL=http://host.docker.internal:11434   # Ollama běží na BrogiServeru (host)
CHROMA_HOST=chromadb
POSTGRES_HOST=postgres
POSTGRES_PORT=5432                             # ← standardní (ne 5433)
```

---

## DEV vs PROD — rozdíly

| Parametr | DEV (MacBook) | PROD |
|---|---|---|
| Docker host | localhost | os01.dxpsolutions.cz |
| Apple Bridge | MacBook host (`host.docker.internal:9100`) | Apple Studio (`10.55.2.117:9100`) |
| Ollama | MacBook host (`host.docker.internal:11434`) | BrogiServer host (`host.docker.internal:11434`) |
| PostgreSQL ext. port | **5433** (conflict fix) | **5432** (standard) |
| Přílohy | bind mount `/Users/pavel/Desktop/OmniFocus` | base64 přes API (scheduler → Apple Bridge) |
| Apple Bridge location | MacBook (stejný stroj jako Docker) | Apple Studio (jiný stroj v LAN) |
| 24/7 provoz | ❌ Mac se uspí | ✅ VPS server |
| Python na Bridge hostu | 3.12+ (MacBook) | 3.9.6 (Apple Studio) — ⚠️ kompatibilita |

---

## SQL migrace

Soubory v `sql/` — spouštět v pořadí při fresh instalaci:

| Soubor | Obsah |
|---|---|
| `001_init.sql` | Základní tabulky (actions, sessions, config, sources) |
| `002_email.sql` | `email_messages` |
| `003_rss.sql` | `rss_articles` |
| `004_youtube.sql` | `youtube_videos` |
| `005_mantis.sql` | `mantis_issues` |
| `006_omnifocus.sql` | `omnifocus_tasks` |
| `007_apple_apps.sql` | `apple_notes`, `apple_reminders`, `apple_contacts`, `calendar_events` |
| `008_classification.sql` | `classification_rules`, `attachments` |
| `009_topics.sql` | `topics`, `topic_signals`, `topic_intersections` |
| `010_imap_status.sql` | `imap_status` |
| `011_claude_sender_verdicts.sql` | `claude_sender_verdicts` ⚠️ SOUBOR CHYBÍ — nutno vytvořit |

⚠️ Tabulka `claude_sender_verdicts` byla na DEV vytvořena ručně přes psql — SQL soubor neexistuje. Vytvořit před PROD migrací.

---

## Testovací příkazy

```bash
# DEV — health checks
curl http://localhost:9100/health          # Apple Bridge
curl http://localhost:9000/               # Dashboard
docker logs brogi_scheduler --tail 20     # Scheduler logy

# PROD — health checks (po nasazení)
curl http://10.55.2.117:9100/health       # Apple Bridge na Apple Studiu
ssh forpsi-root "docker logs brogiasist_scheduler --tail 20"

# SSH přístupy
ssh forpsi-root                           # BrogiServer root
ssh dxpavel@10.55.2.117                   # Apple Studio
```

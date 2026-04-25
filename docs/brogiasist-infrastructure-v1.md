---
Název: Infrastruktura BrogiASIST
Soubor: docs/brogiasist-infrastructure-v1.md
Verze: 2.2
Poslední aktualizace: 2026-04-25
Popis: Stack, servery, porty, sítě, DEV/PROD architektura, databázový stack
Změněno v: 2026-04-25 — upřesněn ChromaDB účel (action learning), přidány Docker compose porty BrogiASIST stacku
---

# Infrastruktura — BrogiASIST

---

## Fyzické stroje

| Stroj | Role | IP (LAN) | OS |
|---|---|---|---|
| MacBook Pro (Paja-MacBook-Pro) | DEV / Claude Desktop | 10.55.2.73 | macOS |
| Mac Studio (PajaAppleStudio) | PROD local / Claude Code | 10.55.2.117 | macOS |
| Synology NAS | n8n server / Docker / NAS | LAN (viz BrogiMAT v5) | DSM |
| BrogiServer | PROD server | WireGuard (Unifi) | stejný pattern jako ostatní PROD projekty |

## Sítě
| Síť | Rozsah | Popis |
|---|---|---|
| LAN domácí | 10.55.2.0/24 | Mac Studio, MacBook, Synology vidí se navzájem |
| Internet | veřejná IP | Příchozí pouze přes Cloudflare Tunnel / WireGuard (Unifi) |
| WireGuard (Unifi) | — | VPN pro PROD |

## Mac Studio — PROD komponenty

### Webhook bridge
| Parametr | Hodnota |
|---|---|
| Umístění | /Users/dxpavel/brogi-webhook/ |
| Soubory | server_v2.py, run-claude.sh, CLAUDE.md |
| Port | 8765 (TCP, 0.0.0.0) |
| Autostart | LaunchAgent: com.brogimat.webhook |
| Plist | /Users/dxpavel/Library/LaunchAgents/com.brogimat.webhook.plist |
| Log | /Users/dxpavel/brogi-webhook/server.log |
| Error log | /Users/dxpavel/brogi-webhook/server.err |
| ThrottleInterval | 10s (ochrana při crash loopu) |

### Claude Code
| Parametr | Hodnota |
|---|---|
| Verze | 2.1.92 |
| Instalace | /usr/local/bin/claude (npm global) |
| Node | /usr/local/bin/node v25.5.0 |
| Účet | dxpavel@me.com (Max předplatné) |
| Billing | Claude Max — ne API kredity |
| Model | Opus 4.6 (1M context) |
| MCP připojeno | Excalidraw, Bitly, Mermaid Chart, Canva |
| MCP potřebuje auth | WordPress.com, Gmail, Google Calendar |
| MCP neaktivní | iMessage (plugin existuje) |
| Adresář projektu | /Users/dxpavel/brogi-webhook/ (CLAUDE.md) |
| Dodatečný adresář | /Volumes/DXPAVEL DRIVE/010 SYNOLOGY DRIVE/001 DXP |
| Session history | /Users/dxpavel/.claude/projects/-Users-dxpavel-brogi-webhook/ |

### PATH fix (systémový)
Soubor /etc/paths.d/node obsahuje `/usr/local/bin` —
zajišťuje že LaunchAgent vidí node při spuštění bez loginshell.

## Databázový stack

### DEV (localhost — Docker compose)

| Služba | Container | Image | Port (host:container) | Účel |
|---|---|---|---|---|
| PostgreSQL | `brogi_postgres` | `postgres:16` | 5433:5432 | Mirror tables, klasifikace, system tabulky |
| ChromaDB | `brogi_chromadb` | `chromadb/chroma` | 8000:8000 | Action learning (collection `email_actions`) |
| Dashboard | `brogi_dashboard` | FastAPI build | 9000:9000 | WebUI |
| Scheduler | `brogi_scheduler` | FastAPI build | 9001:9001 | Ingest + IMAP IDLE + TG callback + ingest API |

| Externí služba | Kde běží | URL z kontejneru |
|---|---|---|
| Apple Bridge | macOS host (launchd) | `http://host.docker.internal:9100` |
| Ollama (Llama3.2 + nomic-embed-text) | macOS host | `http://host.docker.internal:11434` |

⚠️ **Účel ChromaDB v BrogiASIST**: ne semantic search nad maily, ale **action log + pattern matching pro auto-akce** (`find_repeat_action` před TG notifikací). Plnou semantic search je možné dostavět nad stejnou collection.

⚠️ **`actions` tabulka v PostgreSQL** je rezervovaná pro budoucí confirmation workflow — kód do ní nezapisuje, action log běží přes ChromaDB.

### PROD (BrogiServer)
| Služba | Nasazení | Poznámka |
|---|---|---|
| PostgreSQL | Docker | Konfiguruje se až na PROD |
| ChromaDB | Docker | Konfiguruje se až na PROD |
| Apple Bridge | macOS host (launchd) | Stejný launchd plist jako DEV; vyžaduje Full Disk Access pro Calendar |
| Přílohy | připojený Synology mount | Cesta v DB konfiguraci |

### Schema migrace
- Raw SQL v `sql/` (`001_init.sql` … `010_imap_status.sql`)
- Verzované v **GitHub repu**
- Migration tool: zatím manuální `psql -f sql/NNN_*.sql` — Alembic/Flyway TBD

### Zálohy
- TBD — řeší se při konfiguraci PROD
- DEV: backup procedura per `GLOBAL-SKILL.md §11` (`pg_dump → backup/snapshots/YYYYMMDD/`)

---

## Doménová architektura (plán)
| Doména | Stav | Cíl |
|---|---|---|
| assistance.brogi.online | ⏳ nepřipojena | Vstupní bod PROD |
| brogi.online | existuje (BrogiMAT v5) | Referenční konfigurace |

Vzor konfigurace: stejný jako BrogiMAT v5 NUC server
(Cloudflare Tunnel → nginx → interní služby)

## DEV → PROD flow
```
DEV (MacBook Pro + localhost)
  └── Claude Desktop + MCP
  └── Docker: PostgreSQL + ChromaDB (lokální)
  └── Vývoj a testování workflows
  └── Dokumentace v SynologyDrive / GitHub
        ↓ hotovo a otestováno
PROD (Mac Studio + Synology + BrogiServer)
  └── Claude Code (webhook bridge, Mac Studio)
  └── n8n workflows (Synology)
  └── Docker: PostgreSQL + ChromaDB (BrogiServer)
  └── Přílohy: Synology mount
  └── Běží 24/7 jako LaunchAgent
        ↓ veřejný přístup
assistance.brogi.online
  └── Cloudflare Tunnel → nginx → služby
```

## Testovací příkazy
```bash
# Health check (z libovolného stroje na LAN)
curl http://10.55.2.117:8765/health

# Test tasku
curl -X POST http://10.55.2.117:8765/task \
  -H "Content-Type: application/json" \
  -H "X-Brogi-Token: brogi-secret-2026" \
  -d '{"task": "reply with exactly: BROGI_OK"}'

# SSH na Mac Studio
ssh -i ~/.ssh/id_ed25519 dxpavel@10.55.2.117

# Logy webhook serveru
ssh dxpavel@10.55.2.117 tail -f /Users/dxpavel/brogi-webhook/server.log
```

## Výsledky testů (2026-04-06)
| Test | Výsledek |
|---|---|
| Health check localhost | ✅ OK |
| Health check přes síť (10.55.2.117) | ✅ OK |
| POST task BROGI_OK | ✅ odpověď za ~25s |
| Autentizace X-Brogi-Token | ✅ 401 bez tokenu |
| OmniFocus inbox výpis | ✅ 5 reálných úkolů vráceno |
| IMAP brogi@dxpsolutions.cz | ✅ LOGIN OK |
| Restart Mac Studia | ✅ LaunchAgent spustí automaticky |

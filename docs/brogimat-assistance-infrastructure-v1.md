---
Název: Infrastruktura BrogiMatAssistance
Soubor: docs/brogimat-assistance-infrastructure-v1.md
Verze: 2.1
Poslední aktualizace: 2026-04-22
Popis: Stack, servery, porty, sítě, DEV/PROD architektura, databázový stack
Změněno v: 2026-04-22 — přidán databázový stack (PG + ChromaDB), upřesněn PROD server
---

# Infrastruktura — BrogiMatAssistance

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

### DEV (localhost)
| Služba | Nasazení | Poznámka |
|---|---|---|
| PostgreSQL | Docker (lokální) | Staví se od nuly |
| ChromaDB | Docker (lokální) | Pavel má instanci i jinde |
| Přílohy | lokální disk | Cesta v DB konfiguraci |

### PROD (BrogiServer)
| Služba | Nasazení | Poznámka |
|---|---|---|
| PostgreSQL | Docker | Konfiguruje se až na PROD |
| ChromaDB | Docker | Konfiguruje se až na PROD |
| Přílohy | připojený Synology mount | Cesta v DB konfiguraci |

### Schema migrace
- Verzované v **GitHub repu** (raw SQL soubory)
- Migration tool: TBD (raw SQL / Alembic / Flyway — rozhodnutí před první migrací)

### Zálohy
- TBD — řeší se při konfiguraci PROD

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

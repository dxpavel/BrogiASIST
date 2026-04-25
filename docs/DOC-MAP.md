---
Název: DOC-MAP
Soubor: docs/DOC-MAP.md
Verze: 4.1
Poslední aktualizace: 2026-04-25
---

# DOC-MAP — BrogiASIST

---

## Číst na začátku každé session

| Soubor | Popis | Stav |
|---|---|---|
| `CONTEXT-NEW-CHAT.md` | Aktuální stav, cesty, co běží, co chybí | ✅ 2026-04-25 |
| `brogiasist-architecture-v1.md` | Stack, services, endpointy, DB schéma, dataflow, IMAP akce | ✅ 2026-04-25 |
| `brogiasist-lessons-learned-v1.md` | Poučení z praxe — IMAP, JXA, Docker, action logging | ✅ 2026-04-25 |

---

## Referenční dokumentace

| Soubor | Popis | Stav |
|---|---|---|
| `brogiasist-data-dictionary-v1.md` | Datový model, DB tabulky, procesní tok, AI vrstvy | ✅ 2026-04-23 |
| `brogiasist-api-reference-v1.md` | Webhook server endpointy, příklady | ✅ 2026-04-06 |
| `brogiasist-infrastructure-v1.md` | Stroje, porty, sítě, Docker, Apple Bridge | ✅ 2026-04-22 |
| `brogiasist-credentials-v1.md` | Přístupy, API klíče, hesla (nečíst zbytečně) | ✅ 2026-04-22 |
| `brogiasist-workflows-v1.md` | Automatizace, rutiny | ⏳ neaktuální |
| `brogiasist-feature-plan-v1.md` | Původní plán 9 modulů (historický) | ⏳ archiv |

---

## Session procedury

| Soubor | Popis |
|---|---|
| `CONTEXT-NEW-CHAT.md` | Stav projektu — aktualizovat na konci session |

---

## Soubory mimo docs/

| Cesta | Popis |
|---|---|
| `services/dashboard/` | FastAPI dashboard + Jinja2 templates |
| `services/ingest/` | Scheduler, IMAP, Telegram, klasifikace |
| `services/apple-bridge/` | FastAPI bridge pro Apple API (host, port 9100) |
| `sql/` | SQL migrace 001–009 |
| `.env` | Environment proměnné |
| `~/Library/LaunchAgents/cz.brogiasist.apple-bridge.plist` | Autostart Apple Bridge |

---

## Archiv

Soubory v `docs/_archive/` — neaktuální nebo jiný projekt (WordPress).

---
Název: DOC-MAP
Soubor: docs/DOC-MAP.md
Verze: 4.4 (release 1.1)
Poslední aktualizace: 2026-04-26
Pravidlo: Každý dokument v `docs/` musí být v této mapě. Pokud tu není, neexistuje.
---

# DOC-MAP — BrogiASIST

---

## Číst na začátku každé session

| Soubor | Popis | Stav |
|---|---|---|
| `CONTEXT-NEW-CHAT.md` | Aktuální stav, cesty, co běží, co chybí | ✅ 2026-04-25 |
| `brogiasist-architecture-v1.md` | Stack, services, endpointy, DB schéma, dataflow, IMAP akce | ✅ 2026-04-25 |
| `brogiasist-data-dictionary-v1.md` | Datový model, DB tabulky, procesní tok, AI vrstvy | ✅ 2026-04-25 |
| `brogiasist-lessons-learned-v1.md` | Poučení z praxe — IMAP, JXA, Docker, action logging | ✅ 2026-04-25 |
| `brogiasist-infrastructure-v1.md` | Stroje, porty, sítě, Docker, Apple Bridge — **DEV vs PROD** | ✅ 2026-04-26 |
| `BUGS.md` | Známé bugy a tech debt — co opravit, kde, proč. **Aktuálně:** BUG-001/004/005/006 OPEN, BUG-002/003 FIXED v 1.1 | ✅ 2026-04-26 |

---

## Referenční dokumentace

| Soubor | Popis | Stav |
|---|---|---|
| `brogiasist-api-reference-v1.md` | Webhook server endpointy, příklady | ✅ 2026-04-06 |
| `brogiasist-credentials-v1.md` | Přístupy, API klíče, hesla (nečíst zbytečně) | ✅ 2026-04-22 |
| `brogiasist-workflows-v1.md` | Automatizace, rutiny | ⏳ neaktuální |
| `brogiasist-feature-plan-v1.md` | Původní plán 9 modulů | ⏳ archiv (historický) |

---

## Session procedury (handoffs)

| Soubor | Popis |
|---|---|
| `CONTEXT-NEW-CHAT.md` | Stav projektu — aktualizovat na konci session |
| `SESSION-HANDOFF-BRANCH1.md` | Handoff pro branch `1` — implementace base64 příloh (DEV) |
| `PROD-MIGRATION-HANDOFF.md` | Handoff pro PROD migraci — 7 fází (BrogiServer + PajaAppleStudio) |

---

## Datové soubory v `docs/`

| Soubor | Popis | Použití |
|---|---|---|
| `youtube-subscriptions.json` | Snapshot YouTube odběrů (seedovací data) | Vstup pro `ingest_youtube.py` při bootstrapu |

---

## Soubory mimo docs/

| Cesta | Popis |
|---|---|
| `services/dashboard/` | FastAPI dashboard + Jinja2 templates |
| `services/ingest/` | Scheduler, IMAP, Telegram, klasifikace |
| `services/apple-bridge/` | FastAPI bridge pro Apple API (host, port 9100) |
| `sql/` | SQL migrace 001–011 (kompletní, všechny soubory existují) |
| `.env` | Environment proměnné |
| `~/Library/LaunchAgents/cz.brogiasist.apple-bridge.plist` | Autostart Apple Bridge |

---

## Archiv a prázdné složky

| Cesta | Popis |
|---|---|
| `docs/_archive/` | Neaktuální dokumenty — WordPress transfer specs, staré LESSONS-LEARNED, design system v1, webui-spec v1 |
| `docs/modules/` | ⚠️ **Prázdná složka** (vytvořeno 2026-03-26, nikdy nepoužito). Buď doplnit obsah, nebo smazat při příští úklidové session |

---

## Pravidla pro nové dokumenty

1. **Každý nový dokument v `docs/` musí být přidán do DOC-MAP.** Pokud není v DOC-MAP, neexistuje (nikdo ho nenajde).
2. **Při vytváření nového dokumentu:** současně edituj DOC-MAP — přidej řádek do správné sekce s krátkým popisem a stavem.
3. **Při zastarávání dokumentu:** označ stav `⏳ neaktuální` nebo přesuň do `_archive/` + smaž z DOC-MAP.
4. **Datum ve stavu (✅ YYYY-MM-DD):** den poslední smysluplné aktualizace obsahu, ne timestamp filesystému.
5. **Sekce "Číst na začátku každé session"** = soubory které musí znát Claude/vývojář před zápisem do kódu. Změny v této sekci řeší Pavel.

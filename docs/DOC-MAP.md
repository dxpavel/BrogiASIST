---
Název: DOC-MAP
Soubor: docs/DOC-MAP.md
Verze: 4.7 (release v2 patch 2026-04-27)
Poslední aktualizace: 2026-04-27
Pravidlo: Každý dokument v `docs/` musí být v této mapě. Pokud tu není, neexistuje.
---

# DOC-MAP — BrogiASIST

---

## Číst na začátku každé session

| Soubor | Popis | Stav |
|---|---|---|
| `CONTEXT-NEW-CHAT.md` | Aktuální stav, cesty, co běží, co chybí — **branch `2` = v2 in progress** | ✅ 2026-04-26 |
| `SESSION-HANDOFF-D-CONTINUATION.md` | **PRIORITNÍ** handoff pro pokračování blockeru D — HIGH/MEDIUM/LOW priority + první krok | ✅ 2026-04-26 |
| `brogiasist-architecture-v1.md` | Stack, services, endpointy, DB schéma, dataflow, IMAP akce — **vč. v2 komponent (decision_engine, pending_worker) + 2026-04-27 (univerzální 3×3 layout, 2del, predikce-jako-návrh, auto-spam vypnut)** | ✅ 2026-04-27 |
| `brogiasist-data-dictionary-v1.md` | Datový model, DB tabulky, procesní tok, AI vrstvy — **vč. decision_rules + pending_actions + 9. ACTION 2del + endpoint POST /emails/suggested** | ✅ 2026-04-27 |
| `brogiasist-lessons-learned-v1.md` | Poučení z praxe — IMAP, JXA, Docker, action logging, **+ sekce 38** (silent auto-spam race condition), **+ sekce 39** (header_bounce multipart/report) | ✅ 2026-04-27 |
| `brogiasist-infrastructure-v1.md` | Stroje, porty, sítě, Docker, Apple Bridge — **DEV vs PROD** | ✅ 2026-04-26 |
| `brogiasist-semantics-v1.md` | **Email TYP/STATUS/ACTION semantika** — kanonická spec + sekce 21 (implementation status na branch `2`) | ✅ 2026-04-26 v1.2 |
| `BUGS.md` | Známé bugy a tech debt — **BUG-001/004/005/006/009/010 OPEN**, BUG-002/003 FIXED v 1.1, **BUG-007/008 FIXED 2026-04-26** | ✅ 2026-04-26 |

---

## Referenční dokumentace

| Soubor | Popis | Stav |
|---|---|---|
| `brogiasist-api-reference-v1.md` | Webhook server + Apple Bridge endpointy (vč. nových `/of/task/{id}/append_note`, `/notes/{id}/append`, JXA `/contacts/all`) | ✅ 2026-04-26 |
| `brogiasist-credentials-v1.md` | Přístupy, API klíče, hesla (nečíst zbytečně) | ✅ 2026-04-22 |
| `brogiasist-workflows-v1.md` | Automatizace, rutiny | ⏳ neaktuální |
| `brogiasist-feature-plan-v1.md` | Původní plán 9 modulů | ⏳ archiv (historický) |

---

## Session procedury (handoffs)

| Soubor | Popis |
|---|---|
| `CONTEXT-NEW-CHAT.md` | Stav projektu — aktualizovat na konci session |
| `SESSION-HANDOFF-BRANCH1.md` | Handoff pro branch `1` — implementace base64 příloh (DEV) — **DONE 1.1** |
| `SESSION-HANDOFF-PROD.md` | Handoff pro PROD migraci session — startup prompt + co zvážit + co nedělat — **DONE 2026-04-26 (PROD na VM 103)** |
| `PROD-MIGRATION-HANDOFF.md` | Detailní postup migrace — 7 fází (BrogiServer + PajaAppleStudio), autoritativní reference — **DONE** |
| `SESSION-HANDOFF-D-CONTINUATION.md` | **AKTIVNÍ** handoff — pokračování blockeru D na branch `2` (BUG-009/010, threading TG flow, action wiring, calendar reply) |

---

## Datové soubory v `docs/`

| Soubor | Popis | Použití |
|---|---|---|
| `youtube-subscriptions.json` | Snapshot YouTube odběrů (seedovací data) | Vstup pro `ingest_youtube.py` při bootstrapu |

---

## Soubory mimo docs/

| Cesta | Popis |
|---|---|
| `CLAUDE.md` (root) | **Autoritativní projektová pravda** — 16 sekcí (PROD infra VM 103, ENV, deploy, gotchas, TYP/STATUS/ACTION sumár, BUG indexy, commit style). Načítá Claude Code automaticky při startu session. Vyhrává nad memory. (2026-04-26, 2026-04-27 patch) |
| `services/dashboard/` | FastAPI dashboard + Jinja2 templates (v2: kostičky `.typ-box` + grafická semantika sekce 19) + predikce z Chromy v `/úkoly` (2026-04-27) |
| `services/ingest/` | Scheduler, IMAP, Telegram, klasifikace + **decision_engine.py (v2)** + **pending_worker.py (v2)** + **chroma_audit.py / chroma_dedup.py (2026-04-27)** |
| `services/apple-bridge/` | FastAPI bridge pro Apple API (host, port 9100) — **BUG-008 fix `os.posix_spawn()`** + nové endpointy `/of/task/{id}/...`, `/notes/{id}/...`, JXA `/contacts/all` |
| `sql/` | SQL migrace 001–014: 012_apple_contacts_groups.sql, 013_decision_rules.sql, 014_email_semantics_v1.sql (vše v branch `2`) |
| `.env` | Environment proměnné (`OLLAMA_URL`, `APPLE_BRIDGE_URL`, IMAP credentials, ...) |
| `~/Library/LaunchAgents/cz.brogiasist.apple-bridge.plist` | Autostart Apple Bridge — Apple Studio (10.55.2.117) |
| **PROD VM 103 deploy** | `ssh pavel@10.55.2.231` → `cd ~/brogiasist` → `git pull origin 2` → `docker compose build/up` |

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

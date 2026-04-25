---
Název: CONTEXT-NEW-CHAT
Soubor: docs/CONTEXT-NEW-CHAT.md
Verze: 5.1
Poslední aktualizace: 2026-04-25
Popis: Kontext pro nový chat — stav, cesty, problémy
---

# CONTEXT-NEW-CHAT — BrogiASIST

---

## Co projekt je
Osobní asistent pro Pavla — přebírá operativu (emaily, OmniFocus, iMessage,
Mantis, rutiny). Pavel potvrzuje rozhodnutí, asistent vykonává.
Cíl: z 1-2h operativy denně na 10-15 minut.

---

## Aktuální stav (2026-04-25)

### Co běží
- PostgreSQL 16 (Docker, port 5433 external / 5432 internal)
- ChromaDB (Docker, port 8000)
- Dashboard FastAPI + Jinja2 (Docker, port 9000)
- Scheduler APScheduler + IMAP IDLE (Docker, port 9001)
- Apple Bridge FastAPI (na hostu, port 9100, launchd autostart)
- Telegram bot (polling loop v scheduleru, callback handler aktivní)

### Co je implementováno
- IMAP ingest (8 účtů, IDLE push + 30min backup scan)
- RSS ingest (The Old Reader, 30min)
- YouTube ingest (OAuth, 2h)
- MantisBT ingest (30min)
- OmniFocus ingest (Apple Bridge JXA, 10min)
- Apple Notes ingest (30min)
- Apple Reminders ingest (15min)
- Apple Contacts ingest (sqlite, 6h)
- Calendar ingest (AppleScript, 15min)
- Email klasifikace přes Llama3.2 + pravidla (classify_emails.py, 5min)
- Telegram notifikace pro klasifikované emaily s inline tlačítky (notify_emails.py, 2min)
- Telegram callback handler — hotovo/přečteno/čeká/spam/of/rem/note/unsub/skip
- TG: po každé akci se smaže TG zpráva s tlačítky (delete_message)
- TG: `tg_message_id` uložen do DB při notifikaci (sloupec v email_messages)
- Dashboard WebUI: index, pravidla, úkoly, obsah, admin
- Dashboard: proxy route `/api/ingest/email/{id}/action/{action}` → scheduler
- Dashboard /ukoly: plná sada akčních tlačítek pro každý email (nezávisle na AI-typu)
- IMAP akce plně implementovány: mark_read, move_to_trash, move_to_brogi_folder
- Folder routing: NOTIFIKACE→NOTIFIKACE, NEWSLETTER→NEWSLETTER, HOTOVO→HOTOVO atd.
- Apple Bridge status zobrazen na dashboard (zelená/červená)
- Topics/signals systém (témata + signály pro AI matching)
- YouTube scoring proti tématům (stránka /obsah)
- Classification rules (tabulka + WebUI)
- ChromaDB: ukládání akcí pro učení (store_email_action po každé akci)

### Co chybí / TODO
- ChromaDB query layer — `find_repeat_action` běží před notifikací (pattern → auto-akce); další semantic search nad maily zatím nepoužito
- iMessage ingest — sqlite přístup znám, ingest skript chybí
- PROD deployment (BrogiServer / Apple Studio) — běží jen DEV
- Topic intersections UI (v admin formuláři chybí)
- TG `_offset` persistence — po restartu scheduleru se offset resetuje na 0; staré callbacks se ztratí
- `actions` tabulka — placeholder pro confirmation workflow (pending → confirmed → executed); aktuálně **prázdná**, kód nepoužívá
- `email_messages.processed_at` — dead column; logika přechází přes `status` + `folder` + `human_reviewed`

### Action logging — kde se loguje (pozor!)
- **NE** v PostgreSQL `actions` tabulce (prázdná, rezervovaná pro budoucí workflow)
- **ANO** v ChromaDB collection `email_actions` přes `chroma_client.store_email_action()` — embedding (Ollama nomic-embed-text) + metadata (action/typ/firma/mailbox)
- Volá se po každé akci v `imap_actions.py`, `telegram_callback.py`, `api.py`
- Před TG notifikací: `find_repeat_action()` zkontroluje pattern (≥3 podobné s cosine ≤0.15 → auto-akce)

### IMAP ingest — známé transient errors (neblokující)
Občas v lozích:
- `[Errno -3] Try again` (DNS z kontejneru)
- `EOF in violation of protocol (_ssl.c:2437)` (TLS handshake drop)
- `command: LOGIN => socket error: EOF`

Auto-reconnect 30s funguje. Bez zásahu se IDLE obnoví do 5–15 min. Tichý INBOX (např. `brogi@`, `servicedesk@`) ≠ broken ingest — ověř v Mail.app.

---

## Klíčové cesty

| Co | Kde |
|---|---|
| Root projektu | `/Users/pavel/SynologyDrive/001 DXP/009 BrogiASIST/` |
| Dashboard templates | `services/dashboard/templates/` |
| Ingest služby | `services/ingest/` |
| Apple Bridge | `services/apple-bridge/main.py` |
| SQL migrace | `sql/` |
| Dokumentace | `docs/` |
| Apple Bridge launchd plist | `~/Library/LaunchAgents/cz.brogiasist.apple-bridge.plist` |
| Webhook server (Mac Studio) | `/Users/dxpavel/brogi-webhook/` port 8765 |

---

## Aktivní komponenty

| Komponenta | Stav | Kde běží |
|---|---|---|
| PostgreSQL 16 | ✅ běží | Docker brogi_postgres |
| ChromaDB | ✅ běží | Docker brogi_chromadb |
| Dashboard :9000 | ✅ běží | Docker brogi_dashboard |
| Scheduler / IDLE | ✅ běží | Docker brogi_scheduler |
| Apple Bridge :9100 | ✅ běží | Mac host (launchd) |
| Telegram bot | ✅ polling aktivní | v scheduleru |
| Llama klasifikace | ✅ běží | Ollama na hostu |
| Webhook server :8765 | ✅ LaunchAgent | Mac Studio (dxpavel) |

---

## Docker příkazy

```bash
# rebuild jedné služby
docker compose up -d --build dashboard
docker compose up -d --build scheduler

# logy
docker logs brogi_scheduler --tail 30
docker logs brogi_dashboard --tail 30

# SQL přístup
docker exec brogi_postgres psql -U brogi -d assistance -c "SELECT ..."
```

## Apple Bridge restart

```bash
# SPRÁVNĚ (přes launchctl):
launchctl unload ~/Library/LaunchAgents/cz.brogiasist.apple-bridge.plist
launchctl load   ~/Library/LaunchAgents/cz.brogiasist.apple-bridge.plist

# ŠPATNĚ (nezachová autostart):
pkill -f apple-bridge
```

---

## Telegram bot

- Token + Chat ID v `.env`: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`
- Polling loop: `telegram_callback.py:run_callback_loop()` — daemon thread v scheduleru
- Notifikace: `notify_emails.py:notify_classified_emails()` — job každé 2 minuty
- Callback typy: `spam:yes/no:{id}`, `email:hotovo/precteno/ceka/spam/of/rem/note/unsub/skip:{id}`
- Tracking: sloupce `tg_notified_at`, `tg_message_id` v `email_messages`
- Po akci: TG zpráva s tlačítky se automaticky smaže (`delete_message(tg_message_id)`)
- ⚠️ `_offset` není persistentní — restart scheduleru resetuje offset na 0, starší callbacks se ztratí

---

## Topics / Signals systém

- Tabulky: `topics`, `topic_signals`, `topic_intersections`
- Admin WebUI: `/admin`
- Scoring YouTube: `/obsah` — SQL CROSS JOIN s LIKE matching
- Signal typy: positive, negative, brand, system, compatible
- Pravidlo: název tématu = NENÍ automaticky signál — musí být explicitně přidán

---

## Email klasifikace

- Typy: SPAM, NABÍDKA, ÚKOL, INFO, FAKTURA, POTVRZENÍ, NEWSLETTER, NOTIFIKACE, ESHOP
- Firmy: DXPSOLUTIONS, MBANK, ZAMECNICTVI, PRIVATE
- Task statusy: ČEKÁ-NA-MĚ, ČEKÁ-NA-ODPOVĚĎ, →OF, →REM, HOTOVO
- Pravidla: tabulka `classification_rules` — deterministic, před Llama voláním
- Llama model: `llama3.2-vision:11b` přes Ollama (`http://host.docker.internal:11434`)
- Auto-spam threshold: `ai_confidence > 0.92`

## IMAP akce — implementace

- `imap_actions.py`: `mark_read()`, `move_to_trash()`, `move_to_brogi_folder(subfolder)`
- Hledání emailu: primárně přes `imap_uid` z DB; fallback přes Message-ID (source_id)
- Po každé akci se aktualizuje `folder` v DB
- Volá se z: `telegram_callback.py` (TG tlačítka), `api.py` (WebUI tlačítka), `classify_emails.py` (auto-spam)

### Folder routing (BrogiASIST/)
| Akce / Typ | Cílová složka |
|---|---|
| hotovo, →OF, →REM, note | BrogiASIST/HOTOVO |
| precteno + NOTIFIKACE | BrogiASIST/NOTIFIKACE |
| precteno + NEWSLETTER | BrogiASIST/NEWSLETTER |
| precteno + ESHOP | BrogiASIST/ESHOP |
| ceka | BrogiASIST/CEKA |
| spam / unsub | Trash (dle providera) |

### Trash složky dle IMAP hostu
| Host | Trash folder |
|---|---|
| imap.gmail.com | [Gmail]/Trash |
| imap.mail.me.com | Deleted Messages *(musí být quoted v IMAP příkazu)* |
| imap.forpsi.com | INBOX.Trash |
| mail.dxpsolutions.cz | Trash |
| imap.seznam.cz | Trash |

## Backfill skripty

| Skript | Účel |
|---|---|
| `services/ingest/backfill_imap.py` | Zpětný přesun reviewed/spam emailů do BrogiASIST/HOTOVO nebo Trash |
| `services/ingest/backfill_mark_read.py` | Mark as read + přesun pro human_reviewed=TRUE emaily (hledá přes Message-ID) |
| `services/ingest/backfill_spam_read.py` | Přesun is_spam=TRUE (ne reviewed) emailů do Trash; hybridní UID + Message-ID hledání |

Spuštění (v scheduleru kontejneru):
```bash
docker cp services/ingest/backfill_mark_read.py brogi_scheduler:/app/
docker exec brogi_scheduler python backfill_mark_read.py
```

---

## Poslední rozhodnutí

| Datum | Rozhodnutí |
|---|---|
| 2026-04-22 | Stack: PG + ChromaDB v Dockeru, dataflow raw→DB→decide→execute |
| 2026-04-22 | Mirror table + action_log vždy — žádná akce mimo action_log |
| 2026-04-23 | Topics/signals systém navržen a implementován |
| 2026-04-23 | Telegram notifikace s inline tlačítky implementovány |
| 2026-04-23 | Admin stránka oddělena od Pravidla (jiný kontext) |
| 2026-04-23 | YouTube scoring přes keyword matching (ne vektory) — dočasné |
| 2026-04-23 | Apple Bridge restartovat přes launchctl, ne pkill |
| 2026-04-24 | IMAP akce implementovány (mark_read, move_to_trash, move_to_brogi_folder) |
| 2026-04-24 | /ukoly zobrazuje plnou sadu tlačítek — AI klasifikace nezužuje výběr |
| 2026-04-24 | Scheduler port 9001 exposed — dashboard proxy volá ingest API |
| 2026-04-24 | Backfill skripty vytvořeny pro retroaktivní IMAP akce |
| 2026-04-25 | Action logging definitivně přes ChromaDB `email_actions` (ne PG `actions`) — invariant z 2026-04-22 přepsán; `actions` tabulka rezervována pro budoucí confirmation workflow |
| 2026-04-25 | Dokumentace synchronizována s realitou (architecture, lessons-learned, CONTEXT) — `processed_at` dead column, mailbox v DB = email adresa (ne Mail.app display name) |

---

## Lessons learned
→ Viz `docs/brogiasist-lessons-learned-v1.md`

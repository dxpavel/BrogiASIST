# BrogiASIST — Architecture Reference v1

> Stav: 2026-04-25. DEV fáze. DB, ingest, WebUI, klasifikace, IMAP akce, TG callback funkční. AI learning přes ChromaDB. Třívrstvý spam filtr (Llama + kontakty + Claude). PROD deployment plánován.

---

## Stack

| Component | Technology | Port (external) | Port (internal) |
|---|---|---|---|
| Database | PostgreSQL 16 | 5433 (DEV host) | 5432 (Docker network) |
| Vector DB | ChromaDB | 8000 | 8000 |
| Dashboard | FastAPI + Jinja2 | 9000 | 9000 |
| Ingest worker | APScheduler + IMAP IDLE | — | — |
| Apple Bridge | FastAPI (on Mac, NOT Docker) | 9100 | 9100 |
| Orchestration | Docker Compose | — | — |

---

## Services (Docker Compose)

### `postgres`
- Image: `postgres:16`
- Healthcheck: `pg_isready -U brogiasist`
- Volume: `pgdata`
- External port: `5433:5432`
- Env: `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`

### `chromadb`
- Image: `chromadb/chroma`
- **No healthcheck** — image contains no curl or python executable.
- `depends_on` from other services: `condition: service_started` (not `service_healthy`)

### `dashboard`
- FastAPI + Jinja2 templates
- Port: `9000:9000`
- Auto-refresh: 30s (via `<meta http-equiv="refresh">`)
- `depends_on: postgres` (condition: service_healthy)

### `scheduler`
- APScheduler main process + IMAP IDLE daemon threads + Ingest API (port 9001) + TG callback loop
- External port: `9001:9001`
- `depends_on: postgres` (condition: service_healthy)
- ⚠️ Zdrojové soubory jsou baked do image — změny na hostu vyžadují `docker cp` nebo `docker compose up -d --build scheduler`

### `apple-bridge` (NOT in Docker)
- FastAPI service running directly on Mac host
- Managed by launchd: `~/Library/LaunchAgents/cz.brogiasist.apple-bridge.plist`
- Docker services reach it via `http://host.docker.internal:9100`
- Must be running before scheduler starts Apple source jobs

---

## Dataflow

```
Raw sources
    │
    ▼
Ingest scripts (scheduler / apple-bridge)
    │
    ▼
PostgreSQL (mirror tables — email_messages, mantis_issues, …)
    │
    ▼
Klasifikace (classify_emails.py — třívrstvý spam filtr)
  1. classification_rules — manuální pravidla (nejvyšší priorita, i nad kontakty)
  2. POZVÁNKA pravidlo — subject ILIKE 'Invitation:%' → deterministicky, bez Llamy
  3. apple_contacts whitelist — odesílatel v kontaktech → nikdy auto-spam
  4. Llama3.2 → firma / typ / task_status / is_spam / confidence
  5. Spam handling:
     ├─ confidence ≥ 0.92 → auto trash + TG info "🗑️ AUTO-SPAM"
     └─ confidence < 0.92 → Claude Haiku verifikace
          ├─ cache hit (claude_sender_verdicts) → bez API volání
          ├─ Claude spam=True → trash + TG info "🗑️ AUTO-SPAM Claude"
          ├─ Claude spam=False → is_spam=False, normální průchod
          └─ Claude error → fallback TG spam-check
    │
    ▼
Decide:
  ├─ AI auto-akce  (chroma_client.find_repeat_action — pattern match nad email_actions)
  └─ Human review  (Telegram inline tlačítka / Dashboard /ukoly)
    │
    ▼
Execute  (imap_actions.py)
  • mark_read           → IMAP STORE (\Seen) + UPDATE email_messages.status='reviewed'
  • move_to_trash       → IMAP MOVE → Trash + UPDATE folder
  • move_to_brogi_folder → IMAP MOVE → BrogiASIST/<typ> + UPDATE folder
  • of                  → Apple Bridge /omnifocus/add_task (body_text[:1500] + přílohy)
    │
    ▼
Learning  (chroma_client.store_email_action)
  ChromaDB collection "email_actions" — embedding (Ollama nomic-embed-text) + metadata (action/typ/firma/mailbox)
```

**Invariants (stav 2026-04-25):**
- Mirror table vždy zachycuje surová data (raw→DB).
- Každá akce probíhá fyzicky na IMAP a aktualizuje `email_messages.folder` + `status='reviewed'` + `human_reviewed=TRUE`.
- Po každé akci se volá `chroma_client.store_email_action()` → embedding + metadata do ChromaDB pro learning.
- `find_repeat_action()` před notifikací: pokud ≥3 podobné emaily (cosine ≤0.15) měly stejnou akci → automatická exekuce bez TG potvrzení.
- **Pořadí v `_email_action`**: bridge call → DB UPDATE + COMMIT → IMAP move. Nikdy IMAP před commitem — způsobuje row-level lock contention (druhá conn blokuje na UPDATE stejného řádku). Viz lesson #23.
- **Claude sender cache**: každý odesílatel je verifikován přes Claude API maximálně jednou. Výsledek v `claude_sender_verdicts` (PRIMARY KEY = email adresa).
- **Kontakt priorita**: classification_rules (manuální) > apple_contacts (whitelist) > Llama AI.

**Pozn.: dead/reserved schémata** (existují v DB, kód je nepoužívá):
- `actions` tabulka — rezervována pro budoucí confirmation workflow (pending → confirmed → executed). Aktuálně 0 záznamů.
- `email_messages.processed_at` — dead column. Stav drží `status` + `folder` + `human_reviewed`.
- `email_messages.raw_payload` IMAP `\Seen` flag se neukládá — autoritativní zdroj je IMAP server.

---

## Data Sources & Ingest Intervals

| Source | Method | Interval | DB Table |
|---|---|---|---|
| Email (8 accounts) | IMAP IDLE push + 30min backup scan | realtime + 30min | `email_messages` |
| RSS | The Old Reader API | 30min | `rss_articles` |
| YouTube | YouTube Data API v3 (OAuth) | 2h | `youtube_videos` |
| MantisBT | REST API | 30min | `mantis_issues` |
| OmniFocus | Apple Bridge JXA | 10min | `omnifocus_tasks` |
| Apple Notes | Apple Bridge JXA | 30min | `apple_notes` |
| Apple Reminders | Apple Bridge JXA | 15min | `apple_reminders` |
| Apple Contacts | Apple Bridge sqlite | 6h | `apple_contacts` |
| Calendar | Apple Bridge AppleScript | 15min | `calendar_events` |
| iMessage | Apple Bridge sqlite | (planned) | — |

---

## Apple Bridge Architecture

### Proč mimo Docker

Apple API (OmniFocus, Contacts, Calendar, Notes, Reminders, iMessage) jsou přístupné pouze lokálně na macOS přes JXA / AppleScript / sqlite. Docker kontejner na tyto API nemůže přistupovat.

### Provoz

- DEV: běží na vývojovém Macu (launchd autostart)
- PROD: stejný bridge běží na BrogiServer (Apple Studio)
- Docker services: `http://host.docker.internal:9100`

### Endpoints

| Endpoint | Metoda | Popis |
|---|---|---|
| `/health` | GET | Liveness check |
| `/omnifocus/tasks` | GET | Active tasks — JXA `flattenedTasks.whose({completed:false})` |
| `/notes/all` | GET | Všechny poznámky — JXA per-item loop |
| `/reminders/all` | GET | Všechny reminders — JXA |
| `/contacts/all` | GET | Kontakty — přímé čtení sqlite (nejrychlejší) |
| `/calendar/events?days=60` | GET | Události — AppleScript s filtrací kalendářů |

### Launchd plist

```
~/Library/LaunchAgents/cz.brogiasist.apple-bridge.plist
```

Klíčové parametry: `KeepAlive: true`, `RunAtLoad: true`.

---

## DB Schema

### Source mirror tables

| Table | Source |
|---|---|
| `email_messages` | IMAP (8 accounts) |
| `rss_articles` | The Old Reader RSS |
| `youtube_videos` | YouTube Data API |
| `mantis_issues` | MantisBT REST API |
| `omnifocus_tasks` | Apple Bridge / OmniFocus JXA |
| `apple_notes` | Apple Bridge / Notes JXA |
| `apple_reminders` | Apple Bridge / Reminders JXA |
| `apple_contacts` | Apple Bridge / Contacts sqlite |
| `calendar_events` | Apple Bridge / Calendar AppleScript |

### System tables

| Table | Popis |
|---|---|
| `actions` | ⚠️ Rezervováno pro budoucí confirmation workflow — aktuálně **prázdné, kód nepoužívá**. Logging akcí běží přes ChromaDB `email_actions`. |
| `sessions` | Session memory pro AI vrstvu |
| `config` | Key-value konfigurace |
| `sources` | Konfigurace zdrojů (credentials, intervaly) |
| `attachments` | Reference na soubory |
| `classification_rules` | Deterministická pravidla klasifikace (před Llama voláním) |
| `topics`, `topic_signals`, `topic_intersections` | Topic matching pro YouTube/RSS scoring |
| `imap_status` | Per-account IMAP IDLE health (zobrazeno v dashboardu) |

### ChromaDB collections

| Collection | Účel | Embedding |
|---|---|---|
| `email_actions` | Učení pattern → akce (mark_read, hotovo, spam, …). Po každé akci `store_email_action()`. | Ollama `nomic-embed-text`, cosine space |

### WebUI — `/chroma` stránka (dashboard)
- Zobrazuje všechny záznamy v ChromaDB collection `email_actions`
- Filtry: odesílatel (text), akce (dropdown), typ (dropdown)
- Inline editace akce (dropdown + 💾)
- Smazání záznamu (🗑 + confirm dialog)
- Klient-side paginace (25 záznamů na stránku), všechna data načtena najednou
- API: `GET /chroma`, `PATCH /api/chroma/{id}`, `DELETE /api/chroma/{id}`

---

## Email Accounts (8 sledovaných + 1 v náběhu)

| Účet | Provider | Protokol | Port | Pozn. |
|---|---|---|---|---|
| dxpavel@me.com | iCloud | SSL | 993 | fetch: `BODY[]` (ne `RFC822`) |
| brogi@dxpsolutions.cz | Forpsi | STARTTLS | 143 | tichý INBOX, malý objem |
| servicedesk@dxpsolutions.cz | Forpsi | STARTTLS | 143 | tichý INBOX, malý objem |
| support@dxpsolutions.cz | Forpsi | STARTTLS | 143 | — |
| pavel@dxpsolutions.cz | Forpsi | STARTTLS | 143 | — |
| dxpavel@gmail.com | Gmail | SSL | 993 | — |
| padre@seznam.cz | Seznam | SSL | 993 | Bez IDLE — fallback reconnect/30s |
| postapro@dxpavel.cz | Forpsi | STARTTLS | 143 | — |
| zamecnictvi.rozdalovice@gmail.com | Gmail | SSL | 993 | App Password získán, ingestuje |

> iCloud: App-specific password (generuje se na appleid.apple.com → Security → App-specific passwords, formát `xxxx-xxxx-xxxx-xxxx`).

### Známé transient errors (neblokující)

Scheduler logy občas vykazují `[Errno -3] Try again` (DNS) nebo `EOF in violation of protocol (_ssl.c:2437)` při LOGIN. **Auto-reconnect 30s funguje** — během 5–15 min se IDLE obnoví na všech účtech. Není potřeba zásah.

---

## IMAP akce — implementace

`services/ingest/imap_actions.py` — volá se z `telegram_callback.py`, `api.py` (WebUI), `classify_emails.py` (auto-spam) a backfill skriptů.

| Funkce | Co dělá | DB efekt |
|---|---|---|
| `mark_read(email_id)` | IMAP STORE `+FLAGS (\Seen)` | žádný (jen IMAP) |
| `move_to_trash(email_id)` | IMAP MOVE → trash dle providera | `folder`, `status='reviewed'`, `human_reviewed=TRUE` |
| `move_to_brogi_folder(email_id, subfolder)` | IMAP MOVE → `BrogiASIST/<subfolder>` | totéž |
| `action_done(email_id)` | wrapper — volá `mark_read()` | — |

### Folder routing (BrogiASIST/)

| Akce / Typ | Cíl |
|---|---|
| `hotovo`, `→OF`, `→REM`, `note` | `BrogiASIST/HOTOVO` |
| `precteno + NOTIFIKACE` | `BrogiASIST/NOTIFIKACE` |
| `precteno + NEWSLETTER` | `BrogiASIST/NEWSLETTER` |
| `precteno + ESHOP` | `BrogiASIST/ESHOP` |
| `ceka` | `BrogiASIST/CEKA` |
| `spam`, `unsub` | Trash dle providera |

### Trash složky dle hostu

| Host | Trash |
|---|---|
| `imap.gmail.com` | `[Gmail]/Trash` |
| `imap.mail.me.com` | `Deleted Messages` (musí být quoted) |
| `imap.forpsi.com` | `INBOX.Trash` |
| `mail.dxpsolutions.cz` | `Trash` |
| `imap.seznam.cz` | `Trash` |

---

## Backfill skripty

| Skript | Účel |
|---|---|
| `services/ingest/backfill_imap.py` | Zpětný přesun reviewed/spam emailů |
| `services/ingest/backfill_mark_read.py` | Mark as read + přesun pro `human_reviewed=TRUE` (Message-ID search) |
| `services/ingest/backfill_spam_read.py` | Přesun `is_spam=TRUE` (ne reviewed) → Trash; hybridní UID + Message-ID |

Spuštění:
```bash
docker cp services/ingest/backfill_mark_read.py brogi_scheduler:/app/
docker exec brogi_scheduler python backfill_mark_read.py
```

---

## Planned (not yet implemented)

- iMessage ingest (bridge endpoint planned, ingest script chybí)
- WebUI source management (přidání/edit účtů přes UI)
- PROD deployment — BrogiServer (Apple Studio)
- Topic intersections UI (v admin formuláři chybí)
- `actions` tabulka — confirmation workflow (pending → confirmed → executed)
- Apple Bridge notes/add JXA escape bug (speciální znaky → SyntaxError 500; fix: json.dumps)
- Claude API — rozšíření na plnou analýzu (nejen spam verifikace)
- Auto-přidávání classification_rules z opakovaných korekcí

## Implementováno v 2026-04 (tato session)

- **POZVÁNKA pravidlo** — deterministická detekce Google Calendar pozvánek (`subject ILIKE 'Invitation:%'`), bez Llamy
- **Apple Contacts whitelist** — `_is_contact()` v `classify_emails.py`; odesílatel v kontaktech → nikdy auto-spam; manuální pravidla mají vyšší prioritu
- **Claude spam verifikace** — `_claude_verify_spam()` voláno když Llama označí spam s confidence < 0.92; model `claude-haiku-4-5` přes Anthropic API (httpx, bez SDK)
- **Claude sender cache** — `claude_sender_verdicts` tabulka (email PK); každý odesílatel verifikován Claudem maximálně jednou
- **TG auto-spam notifikace** — `🗑️ AUTO-SPAM (X%)` zpráva na TG při automatickém přesunu do koše (Llama jistý nebo Claude potvrdil)
- **Unsub tlačítko v TG** — přidáno do UNIVERSAL_BUTTONS v `notify_emails.py`
- **OF body + přílohy** — `telegram_callback.py`: OF task obsahuje `body_text[:1500]` + přílohy jako `file://` linky v note; pokus o `NSFileWrapper` attach (try/catch)
- **Attachment bind mount** — `/Users/pavel/Desktop/OmniFocus:/app/attachments` v docker-compose.yml
- **ChromaDB WebUI** — `/chroma` stránka v dashboardu (čtení, editace, mazání vzorů)
- **Chroma cleanup** — smazány spam záznamy pro odesílatele v apple_contacts (13 záznamů), Lahoda 3 záznamy ručně

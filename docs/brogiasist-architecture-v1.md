# BrogiASIST — Architecture Reference v1

> Stav: 2026-04-27 (verze 1.2). PROD na VM 103. DB, ingest, WebUI, klasifikace, IMAP akce, TG callback funkční. AI learning přes ChromaDB. Třívrstvý spam filtr (Llama + kontakty + Claude) — **silent auto-spam DOČASNĚ VYPNUTÝ** (race condition incident 2026-04-27). Univerzální 3×3 TG layout, 9 ACTIONs (přidáno 2del). Přílohy do OF přes base64 přenos.

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
  5. Spam handling (⚠️ 2026-04-27: silent auto-trash VYPNUT — `SPAM_AUTO_THRESHOLD=2.0`,
     viz incident s krouzecka@volny.cz, lessons-learned sekce 38):
     ├─ Llama is_spam=TRUE → email PROCHÁZÍ jako normální, Pavel klikne 2spam/2del ručně
     ├─ Claude Haiku verifikace zatím dál běží jako fallback (nebezpečnější část je
     │  silent move_to_trash, ten je vypnutý)
     └─ Po stabilizaci root cause race condition se auto-spam vrátí (TG zpráva
        s tlačítky NE silent execute)
    │
    ▼
Decide:
  ├─ Návrh akce z Chromy (chroma_client.find_repeat_action_with_score — pattern match
  │   nad email_actions; výsledek se NEexekuje silent, ale zobrazí jako zvýrazněné
  │   tlačítko `⭐ 2X ⭐` v TG zprávě a štítek v Dashboard `/úkoly`. 2026-04-27)
  └─ Human review  (Telegram inline tlačítka / Dashboard /úkoly)
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
- `find_repeat_action_with_score()` před notifikací: pokud ≥3 podobné emaily (cosine ≤0.15) měly stejnou akci → **návrh** v TG (zvýrazněné tlačítko `⭐ 2X ⭐` + extra řádek nahoře) a v Dashboard `/úkoly` (žluté tlačítko + štítek `⭐ Navrženo: 2X (NN%)`). Silent auto-execute zrušen 2026-04-27 (incident s `krouzecka@volny.cz`).
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

## SMTP odesílání bot replies (M1, BUG-010 fix, 2026-05-04)

**Spec:** `docs/feature-specs/FEATURE-AI-CASCADE-v1.md` + BUGS.md BUG-010,
varianta **(d) Direct SMTP** (Pavel rozhodnutí 2026-05-04).

Modul: `services/ingest/smtp_send.py` — běží v scheduleru (NE v Apple Bridge).
Důvod: scheduler má `.env` + `ACCOUNTS`, Bridge by potřeboval samostatné
creds + launchd reload. SMTP nepotřebuje Mail.app, jen čistou Python smtplib.

### API

| Funkce | Účel |
|---|---|
| `send_reply(account_name, to, subject, body, in_reply_to=, references=, x_brogi_auto=, html=)` | Pošle email přes SMTP + APPEND kopie do Sent. Vrací `(ok, message_id, error)`. |
| `is_brogi_auto(headers)` | True pokud email má `X-Brogi-Auto` header (= bot vlastní reply, skip ingest/klasifikace) |

### SMTP_MAP per IMAP host

| IMAP host | SMTP host | Port | Security |
|---|---|---|---|
| `imap.gmail.com` | `smtp.gmail.com` | 587 | STARTTLS (App Password) |
| `imap.mail.me.com` | `smtp.mail.me.com` | 587 | STARTTLS (app-specific password) |
| `imap.forpsi.com` | `smtp.forpsi.com` | 587 | STARTTLS |
| `mail.dxpsolutions.cz` | `mail.dxpsolutions.cz` | 587 | STARTTLS (Synology) |
| `imap.seznam.cz` | `smtp.seznam.cz` | 465 | SSL |

**Creds:** stejné jako IMAP (`user` + `password` z `ACCOUNTS`). Login probe
2026-05-04 OK pro všech 5 providerů (smoke test send → vlastní inbox).

### Sent folder per host (pro APPEND)

| IMAP host | Sent folder |
|---|---|
| `imap.gmail.com` | `[Gmail]/Sent Mail` |
| `imap.mail.me.com` | `Sent Messages` |
| `imap.forpsi.com` | `INBOX.Sent` |
| `mail.dxpsolutions.cz` | `INBOX.Sent` |
| `imap.seznam.cz` | `Sent` |

`smtp_send.send_reply()` po úspěšném SMTP odeslání **APPENDuje** kopii
do správného Sent folderu (s `\Seen` flagem) — Pavel pak reply vidí
v Mail.app / Gmail web jako standardní odeslaný email. Pokud APPEND selže
(timeout, no permission), reply je odeslán ale není v Sent — log warning.

### Headers v outbound

Bot reply má vždy:
- `From`: account_name (např. `pavel@dxpsolutions.cz`)
- `To`, `Subject`, `Date` (formatdate localtime)
- `Message-ID` — generovaný `make_msgid(domain="brogiasist")`
- `In-Reply-To` + `References` (RFC 5322 threading)
- **`X-Brogi-Auto`** — string identifikátor akce (např. `"reply"`, `"calendar-accept"`)
- `Auto-Submitted: auto-replied` (RFC 3834)

### Skip ingest pro vlastní reply

Decision rule **`self_sent`** (priority 5, sql/013):
```json
{"condition_type": "header",
 "condition_value": {"header": "X-Brogi-Auto", "operator": "exists"},
 "action_type": "end",
 "action_value": {"skip": true, "reason": "bot_reply"}}
```

`ingest_email.py` extrahuje `X-Brogi-Auto` do `raw_payload.headers` (commit
3304f93). Když email s tímto headerem dorazí (vlastní reply z Sent folderu
přes IMAP IDLE / scan), `decision_engine.evaluate_email()` matchne
`self_sent` → `skip=True` → `classify_new_emails` ho přeskočí. Bot tedy
neflaguje vlastní reply jako úkol.

### Implementováno 2026-05-04 (M1 MVP)

**Akce `thanks` v `email_actions.py`** + TG button `✉️ 2thanks (Díky)`:
- klik → reply "Díky, dostal jsem to.\n\nPavel\n\n--\nOdesláno z BrogiASIST"
  na sender (extracted from `from_address`) z **stejného** mailbox
- subject: `Re: <original>`, In-Reply-To + References = original Message-ID
- X-Brogi-Auto: `thanks`
- po úspěchu: DB `task_status='HOTOVO' status='ZPRACOVANÝ'`, IMAP move BrogiASIST/HOTOVO
- TG: `✉️ Díky reply odeslán → <to_addr>`

TG button se zobrazí **pre-row** nad universal 3×3 jen pro TYPy kde má smysl:
`DOKLAD, INFO, NOTIFIKACE, ÚKOL, FAKTURA, POTVRZENÍ`. Skip pro SPAM/NEWSLETTER/
LIST/ESHOP/ENCRYPTED/POZVÁNKA (POZVÁNKA má vlastní 2cal+Accept v plánu).

### Implementováno 2026-05-04 (M1 final, plný wire)

**Akce `reply` — TG text-input state machine:**
- migrace **020** `tg_pending_replies(chat_id, email_id, started_at, ttl_minutes=30)`
- klik `✏️ 2reply` → record do `tg_pending_replies` + TG prompt "Napiš text odpovědi"
- Pavel pošle text → `telegram_callback._process_text_message` detekuje
  pending state → `send_reply(body=text)` → vyčistí state
- TTL **30 min** (po expiraci pending vyčištěn, Pavel info)
- `/cancel` v TG → bezpečně zruší pending bez odeslání
- po úspěchu: DB ZPRACOVANÝ + IMAP move BrogiASIST/HOTOVO

**Akce `cal_accept` pro POZVÁNKA:**
- klik `📅✉️ 2cal+Accept` → 2 kroky:
  1. CAL event přes Bridge `/calendar/add` (analogicky 2cal akci)
  2. text reply pozvateli "Děkuji za pozvánku, přijímám" (cal-accept marker)
- Plná **RFC 5546 ICS Accept** payload (Method:REPLY + PARTSTAT=ACCEPTED)
  zatím **NE** — odložen, vyžaduje parsovat ICS z původního invitation body.
  MVP text reply funguje pro lidsky zpracované pozvánky.

**TG buttons v `notify_emails._buttons_for_typ`:**
- pre-row pro DOKLAD/INFO/NOTIFIKACE/ÚKOL/FAKTURA/POTVRZENÍ:
  `[✉️ 2thanks] [✏️ 2reply]`
- pre-row pro POZVÁNKA: `[📅✉️ 2cal+Accept]`
- universal 3×3 zachován pod tím

### Plánováno (volitelné, low priority)

- **Plný RFC 5546 ICS Accept** — parsovat původní invitation, generovat
  Method:REPLY ICS payload + content-type: text/calendar; method=REPLY
- **Per-firma signing footer** (DXP / soukromé / mBank …)
- **Reply text z Llama** (bot nabídne navržený text, Pavel ho potvrdí
  nebo upraví) — souvisí s M5 Claude verify cascade

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

## Implementováno v 1.1 (větev `1`, 2026-04-26)

- **Base64 přenos příloh do Apple Bridge** — scheduler čte soubor z disku, base64 encode, posílá v `files: [{filename, content_base64, size_bytes}]` na `POST /omnifocus/add_task`. Limity: 50 MB / soubor, 100 MB / task. Funguje stejně na DEV (1 stroj) i PROD (2 stroje), bez sdíleného filesystemu.
- **Apple Bridge ukládá přílohy** — dekóduje base64 a uloží do `~/Desktop/BrogiAssist/<email_id>/<filename>`. Funguje shodně na MacBook (DEV) i Apple Studio (PROD).
- **file:// linky v OF note** — s `urllib.parse.quote(path, safe='/')` (percent-encoding pro non-ASCII a mezery). Klik v OF otevře PDF v Náhledu.
- **Attachment kaskáda C → B → links_only** — pokus o JXA `make new attachment`, fallback AppleScript `make new attachment`, fallback file:// linky. Diagnostika v response (`attach_method`, `attach_errors`). V OF 4 oba scripting přístupy selhávají (`Can't get object` / `Can't make or move that element into that container`) — v aktuální verzi se vždy končí na `links_only` (vědomé rozhodnutí, viz lessons #32).
- **`backfill_attachments.py`** — re-fetch příloh z IMAP pro emaily kde `has_attachments=TRUE`, `is_spam=FALSE` a v `attachments` 0 řádků. Používá Message-ID search + per-host folder syntaxi.
- **Fix BUG-002** v `ingest_email.upsert_messages` — přílohy se ukládají i pro `is_new=False` (duplicate ON CONFLICT), pokud v `attachments` ještě nejsou a email NENÍ spam.
- **`ensure_brogi_folders.py`** — idempotentní vytvoření kompletní BrogiASIST hierarchie na všech IMAP účtech (mitigace BUG-004 — Forpsi a Synology účty žádné `BrogiASIST/*` neměly).

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

## Implementováno v 2026-04-26 (branch `2` — release v2)

### BUG-008 fix — Apple Bridge fork() crash
- Multi-threaded fork() bug v Network.framework atfork hook → Bridge náhodně padal s SIGSEGV
- Workaround #1 (`OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES`) na macOS 26.4.1 nefunguje
- **Proper fix:** `os.posix_spawn()` v `services/apple-bridge/main.py:_spawn_osascript()` — atomický syscall, neforkuje, atfork hooks se nevolají
- Verifikováno: 50 requestů × 21 minut zátěže → 0 crashů
- Lessons learned sekce 35

### Email Semantics v1 spec — kanonický referenční dokument
- `docs/brogiasist-semantics-v1.md` — 9 TYPů, 5 STATUS, 8 ACTION + 2undo (prefix `2` = "to")
- 19 skupin Apple Contacts jako orthogonal signál
- decision_rules engine, RFC 5322 threading, email↔OF linking, failure handling
- Grafická specifikace (kostičky/fill/kazeťák symboly)

### Blocker A — RFC 5322 headers v ingest
- `services/ingest/ingest_email.py` ukládá 13 hlaviček do `raw_payload.headers` (Message-ID, In-Reply-To, References, List-Id, List-Unsubscribe, List-Post, Auto-Submitted, Content-Type, Cc, Bcc, Reply-To, Return-Path, X-Mailer)
- Pre-AI detekce LIST/ENCRYPTED/INFO-OOO/ERROR-bounce možná

### Blocker B — Apple Contacts groups (orthogonal signál)
- Apple Bridge `/contacts/all` přepsáno z direct sqlite na **JXA** (FDA limitations pro launchd-spawned procesy — viz lessons sekce 36)
- Endpoint vrací `groups: [...]` per kontakt (mapping přes `contacts.groups()` + `g.people()`)
- DB schema `apple_contacts.groups jsonb` + GIN index (sql/012)
- `ingest_apple_apps.ingest_contacts()` — hash check (sha256) → skip pokud žádné změny od minulého ingestu
- Interval 12h (Pavel: 2× denně stačí)
- 🍎 BUG-009 OPEN: data ve 2 disjoint datasets (starý DEV vs nový PROD), group rules zatím nematchují

### Blocker C — `decision_rules` engine
- `sql/013_decision_rules.sql` — schema + 9 default pravidel (priority 5–80)
- `services/ingest/decision_engine.py` — `evaluate_email(email)` → decision dict
- Integrace v `classify_emails.py:classify_new_emails()` — engine PŘED Llamou
- Condition types: header (exists/equals/contains), group, sender, chroma, ai_fallback
- Action types: end (set TYP/action + stop pipeline), flag (continue), apply_remembered (chroma), run_llama
- Verifikováno: 25 emailů, 1× header_list, 4× chroma_match, 20× ai_fallback

### Blocker D1 — schema rozšíření + threading
- `sql/014_email_semantics_v1.sql`:
  - `email_messages` přidat: `message_id`, `in_reply_to`, `thread_id`, `of_task_id`, `of_linked_at`, `is_personal`
  - 3 partial indexy
  - **Nová tabulka `pending_actions`** (queue pro degraded mode)
- Threading: `ingest_email.upsert_messages` JOIN přes message_id → zděd thread_id

### Blocker D2 — Llama prompt + per-TYP TG tlačítka
- Llama prompt: 6 TYPů (ÚKOL/DOKLAD/NABÍDKA/NOTIFIKACE/POZVÁNKA/INFO)
- ERROR/LIST/ENCRYPTED detekuje engine PŘED Llamou
- Body 400 → 500 znaků (per spec M5)
- `notify_emails._buttons_for_typ(typ, email_id, has_unsubscribe)` — per spec sekce 7
- Backward compat: callback_data zůstává `email:<action>:<id>`

### Blocker D3 (4/6 endpointů) — Apple Bridge nové
- `GET /omnifocus/task/{task_id}` — fetch task properties
- `POST /omnifocus/task/{task_id}/append_note` — append k OF notes
- `GET /notes/{note_id}` — fetch Apple Notes note
- `POST /notes/{note_id}/append` — HTML-safe append k Notes body
- TODO: `/calendar/reply`, `/mail/send` (BUG-010 — Mail.app neumí custom headers)

### Blocker D4 — CLS fix + grafická spec
- Google Fonts `display=swap` → `display=optional` (žádný late font swap)
- Logo `<img>` dostal explicit width/height (žádný layout shift)
- 9 CSS variables `--typ-*`, 9 `--action-*`, 5 `--status-*`
- Třídy `.typ-box`, `.action-btn`, `.status-circle` v base.html
- Email tabulka v index.html: kostičky `.typ-box` per TYP + 9 nových filter chips

### Blocker D5 — pending queue worker (degraded mode)
- `services/ingest/pending_worker.py`:
  - `bridge_health()` — aktivní /health ping
  - `enqueue(...)` — INSERT do pending_actions
  - `drain_queue()` — SELECT pending, throttle 2s, retry 3×
- `_bridge_call` v telegram_callback: connection error → enqueue + True (TG „⏳ ve frontě")
- Scheduler job `drain_queue` interval 1 min

## Nové komponenty v branch `2`

| Modul | Účel |
|---|---|
| `services/ingest/decision_engine.py` | Konfigurovatelný rozhodovací stroj — 9 pravidel z DB, runs PŘED Llamou |
| `services/ingest/pending_worker.py` | Queue pro Apple Bridge offline (degraded mode) — bridge_health, enqueue, drain_queue |
| `sql/012_apple_contacts_groups.sql` | apple_contacts.groups jsonb + GIN index |
| `sql/013_decision_rules.sql` | decision_rules tabulka + 9 default pravidel |
| `sql/014_email_semantics_v1.sql` | email_messages threading + flags + pending_actions tabulka |

## Implementováno 2026-04-27 (branch `2`)

- **Univerzální 3×3 TG layout** — předchozí per-TYP redukce nahrazena jednotným layoutem (řada 1: 2hotovo/2of/2rem; řada 2: 2cal/2note/2unsub*; řada 3: 2skip/2del/2spam). 2unsub se zobrazí jen pro maily s `List-Unsubscribe` headerem. ENCRYPTED má extra řádek `👁 Otevřu sám`. Detail v `notify_emails._buttons_for_typ`.
- **Nová ACTION 2del** — univerzální „rychle smazat" (duplicity, šum). Přesun do Trash + Chroma `email_actions` log, ale **NE**zapisuje `classification_rules` (na rozdíl od `2spam`). Handler v `telegram_callback._email_action` (action="del"). 9 ACTIONs celkem.
- **Predikce z Chromy jako návrh (TG + Dashboard)** — místo silent auto-apply se zobrazí zvýrazněné tlačítko `⭐ 2X ⭐` v TG (extra řádek nahoře + 3×3 hvězdičky) a žluté tlačítko + štítek v Dashboard `/úkoly`. Nový endpoint `POST /emails/suggested` v `services/ingest/api.py` (body `{ids: [uuid,...]}` → `{id: {action, confidence_pct} | None}`). Dashboard `/úkoly` route fail-soft (timeout 10s, bez predikce UI funguje dál). Funkce `chroma_client.find_repeat_action_with_score` (backward-compat wrapper `find_repeat_action` zachován).
- **Auto-spam VYPNUT (dočasně)** — `SPAM_AUTO_THRESHOLD=2.0` (= nikdy). Race condition v `classify_emails.py` zničil legitimní email od účetní (Apple Contacts whitelist nematchnul kvůli „Siri found in Mail" emailu). Pavel klikne 2spam/2del ručně. Učení v Chromě dál funguje, jen bez auto-execute.
- **header_bounce pravidlo opraveno** — podmínka přepnuta z `Auto-Submitted: auto-generated` (matchovala MantisBT/GitHub/monitoring) na `Content-Type: multipart/report` (RFC 3464 standard pro Delivery Status Notifications). Změna v `sql/013_decision_rules.sql` + DB update na PROD VM 103.
- **Chroma audit/dedup nástroje** — `services/ingest/chroma_audit.py` (read-only detekce 5 typů problémů: D1 duplicity, D2 protichůdné akce, D3 stale records, D4 whitelist konflikt, D5 sirotci) + `services/ingest/chroma_dedup.py` (deduplikace D1; `--dry-run` default, `--apply` skutečné smazání). První audit (2026-04-26): 132 → 113 záznamů po smazání 19 duplicit.
- **CLAUDE.md v rootu repa** — autoritativní projektová pravda (16 sekcí: PROD infra VM 103, ENV, deploy workflows, gotchas, TYP/STATUS/ACTION sumár, BUG indexy, commit style). Načítá se automaticky na startu každé Claude Code session.

## Nové komponenty 2026-04-27

| Modul / Soubor | Účel |
|---|---|
| `services/ingest/chroma_audit.py` | Read-only detekce 5 typů problémů v ChromaDB `email_actions` |
| `services/ingest/chroma_dedup.py` | Deduplikace D1 (stejný sender + normalizovaný subject) — preferuje human_corrected, nejnovější |
| `services/ingest/api.py:POST /emails/suggested` | Batch endpoint pro Dashboard `/úkoly` predikce z Chromy |
| `chroma_client.find_repeat_action_with_score` | Vrací (action, match_count, total_close) pro UI návrhy |

---

## AI rozhodovací proces — strukturální safety (2026-05-06)

**Základní pravidlo (Pavlovo rozhodnutí po Škoda incidentu):**
**AI NIKDY nerozhoduje `is_spam`.** AI je read-only klasifikátor TYPu, ne
autorita. Pravidla a spam decision = 100 % Pavlovo (klik / WebUI / Contacts).

### Decision flow per email

```
Email přijde → ingest_email.py
       ↓
decision_engine.evaluate_email()
  ├── header rules (LIST, ENCRYPTED, ERROR/bounce, OOO) → end_pipeline
  ├── self_sent (X-Brogi-Auto) → skip
  ├── group rules (VIP / personal) → flag
  ├── chroma_match (cosine ≤ 0.15 = ~85% similarity) → apply_remembered
  └── ai_fallback (priority 80) → run_llama
       ↓
classify_emails.py
  ├── _is_contact(sender) → in_contacts=True (whitelist)
  ├── classification_rules (sender memory) — naučené z Pavlových kliků
  ├── Llama klasifikace TYP (NE is_spam)
  │     ↓
  │   is_spam = False vždy (Llama output ignore)
  │     ↓
  │   uloží: typ, task_status, ai_confidence, ai_source
  └── 2026-05-06: žádný auto-trash z AI, žádný Claude verify spam
       ↓
notify_emails.py → TG zpráva + buttons:
  - in_contacts=False → pre-row [📇 2contact (BROGI)]
  - DOKLAD/INFO/... → pre-row [✉️ 2thanks] [✏️ 2reply]
  - POZVÁNKA → pre-row [📅✉️ 2cal+Accept]
  - universal 3×3 (hotovo/of/rem/cal/note/unsub/skip/del/spam)
       ↓
Pavel klikne → email_actions.email_action()
  ├── 2spam → mark_spam (is_spam=TRUE) + classification_rules INSERT
  │           + IMAP Trash + Chroma store_email_action
  ├── 2del → IMAP Trash (NE classification_rules, NE is_spam)
  ├── 2contact → Bridge /contacts/add (group=BROGI) + ingest_contacts
  └── ostatní → IMAP move BrogiASIST/* + DB ZPRACOVANÝ + Chroma store
```

### Spam decision — JEN explicit signály

| Signál | Co dělá |
|---|---|
| Pavel klik **`🚫 2spam`** v TG | `is_spam=TRUE`, INSERT do `classification_rules`, IMAP Trash |
| `classification_rules` rule_type='spam' (sender match) | classify pipeline → `is_spam=TRUE` + auto-Trash |
| `decision_rules` sender exact match (manuální blacklist v `/pravidla`) | end_pipeline + skip |

### Whitelist — Apple Contacts (univerzální)

Místo hardcoded domén (gov.cz / financnisprava.cz / ...) → **Apple Contacts
skupina BROGI** jako trusted whitelist.

- `_is_contact(from_addr)` v classify_emails ověřuje v `apple_contacts.emails`
- Pavel přidává sendery klikem **`📇 2contact (BROGI)`** v TG (pre-row
  zobrazený pokud sender NENÍ v kontaktech)
- Bridge `/contacts/add` JXA → Apple Contacts.app + group BROGI
- `ingest_contacts()` triggered hned → DB sync (apple_contacts.emails + groups)
- Příští email od stejného sendera → in_contacts=True → konzervativní flow

### Plánováno (M5 session 3, ~6 h)

Claude Haiku 4.5 verifikace TYPu (NE spam) s kontextem:
- Pavlovy topics (z `topics` tabulky, `/admin` editor)
- Pavlovy skupiny kontaktů (Apple Contacts groups)
- Co Pavel naposled rozhodl pro podobné emaily (Chroma)

Trigger: pokud Llama confidence < `CLAUDE_VERIFY_THRESHOLD` (default 0.90).

**NIKDY nerozhoduje is_spam** — jen vrátí TYP, topics, suggested_action,
suggested_task_title/due. Spam zůstává 100 % manuální.

---

## Verze systému — VERSION soubor (2026-05-04)

Single source of truth pro verzi systému: `VERSION` text soubor v **repo rootu**
(jediný řádek, např. `2.0`).

### Konzumace

| Kde | Jak |
|---|---|
| Dashboard (`services/dashboard/main.py`) | `_load_version()` čte z 3 fallback paths (`../../VERSION` lokálně, `/app/VERSION` v containeru, `./VERSION` jako sib) → set `templates.env.globals["app_version"]` při startu |
| `base.html` nav badge | `<span class="nav-badge">v{{ app_version }}</span>` (dynamic) — viditelné v levém horním rohu vedle loga |
| Container | bind mount `./VERSION:/app/VERSION:ro` v `docker-compose.yml` (dashboard service) |

### Bump verze (= bez rebuildu)

```bash
echo "2.1" > VERSION
docker compose restart dashboard       # bind mount → reload, NE rebuild
git add VERSION && git commit -m "chore: bump v2.1"
```

Ostatní moduly (scheduler, Apple Bridge) zatím verzi nezobrazují — případné
budoucí zobrazení v `/admin` nebo TG hlavičce může číst stejný soubor stejně.

### Inspirace

Analogicky k BrogiMAT (`web/www/index.html` → `<span class="header-tag">v3.0-dev</span>`).
Pavlův požadavek 2026-05-04: konzistentní zobrazení verze napříč brogi-* projekty.

### Lekce #55

Anti-pattern: hardcoded verze v Dockerfile `ENV` / template = každý bump
vyžaduje rebuild + redeploy. Bind mount + restart = sekundy.

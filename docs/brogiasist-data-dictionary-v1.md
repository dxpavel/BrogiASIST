---
Název: Datový a procesní slovník BrogiASIST
Soubor: docs/brogiasist-data-dictionary-v1.md
Verze: 4.1
Poslední aktualizace: 2026-04-25
Popis: DB schéma, procesní tok, AI vrstvy, Telegram pipeline — podle reality v kódu
---

# Datový a procesní slovník — BrogiASIST

---

## Universální dataflow

```
ZDROJ (IMAP / RSS / YouTube / Mantis / Apple apps)
  │
  ▼ INGEST (scheduler / apple-bridge)
raw kopie → PostgreSQL (mirror tabulka)
  │
  ▼ KLASIFIKACE (classify_emails.py — třívrstvý spam filtr)
  1. classification_rules (manuální pravidla — nejvyšší priorita, i nad kontakty)
  2a. POZVÁNKA pravidlo — subject ILIKE 'Invitation:%' → bez Llamy
  2b. spam pravidla z classification_rules → trash
  2c. apple_contacts whitelist — odesílatel v kontaktech → blokuje AI spam
  3. Llama3.2 přes Ollama → firma / typ / task_status / is_spam / confidence
  4. Kontakt override: in_contacts AND is_spam → is_spam=False
  5. Spam handling:
     ├─ confidence ≥ 0.92 → auto trash + TG "🗑️ AUTO-SPAM"
     └─ confidence < 0.92 → Claude Haiku verifikace (claude_sender_verdicts cache)
          ├─ spam=True → trash + TG "🗑️ AUTO-SPAM Claude"
          ├─ spam=False → is_spam=False, normální průchod
          └─ error → fallback TG spam-check
  │
  ▼ DECIDE
Auto-akce: chroma_client.find_repeat_action (≥3 podobné, cosine ≤0.15)
Human review: notify_emails.py → Telegram inline tlačítka
  │
  ▼ EXECUTE (telegram_callback.py / api.py / classify_emails.py)
hotovo / přečteno / spam / of / rem / note / unsub / skip / cal
  │  imap_actions: mark_read | move_to_trash | move_to_brogi_folder
  │  DB update: folder, status='reviewed', human_reviewed=TRUE
  │  of: Apple Bridge /omnifocus/add_task (body_text[:1500] + file:// přílohy)
  │
  ▼ LEARN
chroma_client.store_email_action → ChromaDB collection "email_actions"
(embedding nomic-embed-text + metadata: action/typ/firma/mailbox)
```

**Invariant (stav 2026-04-25):**
- Mirror tabulka zachycuje raw data vždy.
- Každá akce probíhá fyzicky na IMAP a aktualizuje `email_messages.folder` + `status='reviewed'` + `human_reviewed=TRUE`.
- Po každé akci se volá `chroma_client.store_email_action()` → ChromaDB pro learning.
- ⚠️ PostgreSQL `actions` tabulka **NENÍ** action log — je rezervovaná pro budoucí confirmation workflow (kód do ní nezapisuje).

---

## Zdroje dat a ingest intervaly

| Zdroj | Metoda | Interval | Mirror tabulka |
|---|---|---|---|
| Email (8 účtů) | IMAP IDLE push + 30min backup scan | realtime + 30min | `email_messages` |
| RSS | The Old Reader API | 30min | `rss_articles` |
| YouTube | YouTube Data API v3 (OAuth) | 2h | `youtube_videos` |
| MantisBT | REST API | 30min | `mantis_issues` |
| OmniFocus | Apple Bridge JXA bulk fetch | 10min | `omnifocus_tasks` |
| Apple Notes | Apple Bridge JXA | 30min | `apple_notes` |
| Apple Reminders | Apple Bridge JXA | 15min | `apple_reminders` |
| Apple Contacts | Apple Bridge sqlite přímý přístup | 6h | `apple_contacts` |
| Calendar | Apple Bridge CalDAV API (iCloud) | 15min | `calendar_events` |
| iMessage | plánováno — Apple Bridge sqlite | — | — |

---

## DB tabulky — mirror

### `email_messages` (migrace 002 + 008)

| Sloupec | Typ | Popis |
|---|---|---|
| `id` | UUID PK | gen_random_uuid() |
| `source_type` | VARCHAR | vždy `'email'` |
| `source_id` | VARCHAR UNIQUE | Message-ID hlavičky |
| `raw_payload` | JSONB | celá MIME zpráva (⚠️ neobsahuje `\Seen` flag — autoritativní zdroj je IMAP server) |
| `ingested_at` | TIMESTAMPTZ | kdy staženo |
| `status` | VARCHAR | `new` / `classified` / `reviewed` / `unsubscribed` |
| `processed_at` | TIMESTAMPTZ | ⚠️ **dead column** — nezapisuje se. Stav drží `status` + `folder` + `human_reviewed` |
| `mailbox` | VARCHAR | **emailová adresa** schránky (brogi@dxpsolutions.cz atd.) — **ne** display name z Mail.app |
| `from_address` | VARCHAR | odesílatel |
| `to_addresses` | TEXT[] | pole příjemců |
| `subject` | VARCHAR | předmět |
| `sent_at` | TIMESTAMPTZ | datum odeslání |
| `has_attachments` | BOOLEAN | má přílohy |
| `folder` | VARCHAR | IMAP složka (default `INBOX`); po akci `BrogiASIST/<typ>` nebo Trash |
| `imap_uid` | BIGINT | IMAP UID pro akce (move, mark read) |
| `firma` | VARCHAR | `DXPSOLUTIONS` / `MBANK` / `ZAMECNICTVI` / `PRIVATE` |
| `typ` | VARCHAR | `SPAM` / `NABÍDKA` / `ÚKOL` / `INFO` / `FAKTURA` / `POTVRZENÍ` / `NEWSLETTER` / `NOTIFIKACE` / `ESHOP` |
| `task_status` | VARCHAR | `ČEKÁ-NA-MĚ` / `ČEKÁ-NA-ODPOVĚĎ` / `→OF` / `→REM` / `HOTOVO` |
| `is_spam` | BOOLEAN | spam flag |
| `ai_confidence` | FLOAT | skóre Llama (0.0–1.0) |
| `human_reviewed` | BOOLEAN | Pavel potvrdil (TRUE i po auto-akci přes find_repeat_action) |
| `body_text` | TEXT | extrahovaný text (pro embedding + UI náhled) |
| `unsubscribe_url` | TEXT | URL pro odhlášení (z hlavičky List-Unsubscribe) |
| `tg_notified_at` | TIMESTAMPTZ | kdy odeslána TG notifikace (NULL = ještě ne) |
| `tg_message_id` | INTEGER | ID TG zprávy s tlačítky — pro pozdější `delete_message` po akci |

Indexy: `status`, `mailbox`, `sent_at DESC`, `from_address`, `is_spam`, `firma`, `typ`

---

### `rss_articles` (migrace 003)

| Sloupec | Typ | Popis |
|---|---|---|
| `id` | UUID PK | |
| `source_type` | VARCHAR | vždy `'rss'` |
| `source_id` | VARCHAR UNIQUE | The Old Reader item ID |
| `raw_payload` | JSONB | |
| `ingested_at` | TIMESTAMPTZ | |
| `status` | VARCHAR | `new` / `analyzed` |
| `processed_at` | TIMESTAMPTZ | |
| `feed_id` | VARCHAR | ID feedu v The Old Reader |
| `feed_title` | VARCHAR | název feedu |
| `title` | VARCHAR | titulek článku |
| `url` | VARCHAR | odkaz na článek |
| `author` | VARCHAR | autor |
| `published_at` | TIMESTAMPTZ | datum publikace |
| `is_read` | BOOLEAN | přečteno |
| `is_starred` | BOOLEAN | označeno hvězdou |
| `summary` | TEXT | výtah obsahu |

Indexy: `status`, `published_at DESC`, `feed_id`, `is_read`

---

### `youtube_videos` (migrace 004)

| Sloupec | Typ | Popis |
|---|---|---|
| `id` | UUID PK | |
| `source_type` | VARCHAR | vždy `'youtube'` |
| `source_id` | VARCHAR UNIQUE | YouTube video ID |
| `raw_payload` | JSONB | |
| `ingested_at` | TIMESTAMPTZ | |
| `status` | VARCHAR | `new` / `analyzed` |
| `processed_at` | TIMESTAMPTZ | |
| `channel_id` | VARCHAR | YouTube channel ID |
| `channel_title` | VARCHAR | název kanálu |
| `title` | VARCHAR | titulek videa |
| `url` | VARCHAR | odkaz (`https://youtube.com/watch?v=...`) |
| `published_at` | TIMESTAMPTZ | datum publikace |
| `duration_sec` | INTEGER | délka v sekundách |
| `view_count` | BIGINT | počet zhlédnutí |
| `description` | TEXT | popis videa |

Indexy: `status`, `published_at DESC`, `channel_id`

---

### `mantis_issues` (migrace 005)

| Sloupec | Typ | Popis |
|---|---|---|
| `id` | UUID PK | |
| `source_type` | VARCHAR | vždy `'mantis'` |
| `source_id` | VARCHAR UNIQUE | MantisBT issue ID |
| `raw_payload` | JSONB | |
| `ingested_at` | TIMESTAMPTZ | |
| `status` | VARCHAR | `new` / `analyzed` |
| `processed_at` | TIMESTAMPTZ | |
| `project_id` | INTEGER | MantisBT project ID |
| `project_name` | VARCHAR | název projektu |
| `summary` | VARCHAR | shrnutí ticketu |
| `description` | TEXT | popis |
| `issue_status` | VARCHAR | stav ticketu (new, assigned, resolved…) |
| `priority` | VARCHAR | priorita |
| `severity` | VARCHAR | závažnost |
| `reporter` | VARCHAR | kdo nahlásil |
| `assigned_to` | VARCHAR | přiřazeno |
| `created_at` | TIMESTAMPTZ | kdy vznikl ticket |
| `updated_at` | TIMESTAMPTZ | poslední změna |

Indexy: `status`, `project_id`, `updated_at DESC`, `issue_status`

---

### `omnifocus_tasks` (migrace 006)

| Sloupec | Typ | Popis |
|---|---|---|
| `id` | SERIAL PK | |
| `source_type` | VARCHAR | vždy `'omnifocus'` |
| `source_id` | VARCHAR UNIQUE | OmniFocus task ID |
| `name` | VARCHAR | název tasku |
| `project` | VARCHAR | projekt |
| `status` | VARCHAR | `available` / `next` / `blocked` / `due_soon` / `overdue` / `completed` / `dropped` |
| `flagged` | BOOLEAN | označen vlajkou |
| `due_at` | TIMESTAMPTZ | termín |
| `defer_at` | TIMESTAMPTZ | odloženo do |
| `completed_at` | TIMESTAMPTZ | kdy dokončeno |
| `modified_at` | TIMESTAMPTZ | poslední změna v OF |
| `tags` | JSONB | pole tagů `[]` |
| `note` | TEXT | poznámka |
| `in_inbox` | BOOLEAN | je v inboxu |
| `raw_payload` | JSONB | |
| `ingested_at` | TIMESTAMPTZ | |
| `processed_at` | TIMESTAMPTZ | |
| `status_proc` | VARCHAR | `new` / `analyzed` / `ignored` |

Indexy: `status`, `due_at WHERE NOT NULL`, `flagged WHERE TRUE`

---

### `apple_notes` (migrace 007)

| Sloupec | Typ | Popis |
|---|---|---|
| `id` | SERIAL PK | |
| `source_type` | VARCHAR | vždy `'apple_notes'` |
| `source_id` | VARCHAR UNIQUE | Notes item ID |
| `name` | VARCHAR | název poznámky |
| `body` | TEXT | obsah (max 2000 znaků z Apple Bridge) |
| `modified_at` | TIMESTAMPTZ | |
| `created_at` | TIMESTAMPTZ | |
| `ingested_at` | TIMESTAMPTZ | |
| `status` | VARCHAR | `new` |

---

### `apple_reminders` (migrace 007)

| Sloupec | Typ | Popis |
|---|---|---|
| `id` | SERIAL PK | |
| `source_type` | VARCHAR | vždy `'apple_reminders'` |
| `source_id` | VARCHAR UNIQUE | Reminders item ID |
| `name` | VARCHAR | název připomínky |
| `list_name` | VARCHAR | název seznamu |
| `body` | TEXT | poznámka |
| `flagged` | BOOLEAN | |
| `completed` | BOOLEAN | |
| `due_at` | TIMESTAMPTZ | termín |
| `remind_at` | TIMESTAMPTZ | čas připomenutí |
| `modified_at` | TIMESTAMPTZ | |
| `ingested_at` | TIMESTAMPTZ | |
| `status` | VARCHAR | `new` |

Index: `due_at WHERE NOT NULL`

---

### `apple_contacts` (migrace 007)

| Sloupec | Typ | Popis |
|---|---|---|
| `id` | SERIAL PK | |
| `source_type` | VARCHAR | vždy `'apple_contacts'` |
| `source_id` | VARCHAR UNIQUE | AddressBook ZUNIQUEID |
| `first_name` | VARCHAR | jméno |
| `last_name` | VARCHAR | příjmení |
| `organization` | VARCHAR | firma |
| `emails` | JSONB | `[{"label": "...", "value": "..."}]` |
| `phones` | JSONB | `[{"label": "...", "value": "..."}]` |
| `modified_at` | TIMESTAMPTZ | |
| `ingested_at` | TIMESTAMPTZ | |

Index: `last_name, first_name`

---

### `calendar_events` (migrace 007)

| Sloupec | Typ | Popis |
|---|---|---|
| `id` | SERIAL PK | |
| `source_type` | VARCHAR | vždy `'calendar'` |
| `source_id` | VARCHAR UNIQUE | `{UID}_{start_iso}` |
| `summary` | VARCHAR | název události |
| `calendar` | VARCHAR | název kalendáře |
| `start_at` | TIMESTAMPTZ | začátek |
| `end_at` | TIMESTAMPTZ | konec |
| `all_day` | BOOLEAN | celý den |
| `location` | VARCHAR | místo |
| `ingested_at` | TIMESTAMPTZ | |
| `status` | VARCHAR | `new` |

Index: `start_at`

---

## DB tabulky — systémové

### `actions` (migrace 001) — ⚠️ aktuálně nepoužívána

| Sloupec | Typ | Popis |
|---|---|---|
| `id` | UUID PK | |
| `source_type` | VARCHAR | `email` / `mantis` / `youtube` / … |
| `source_id` | VARCHAR | FK na zdrojový záznam |
| `action_type` | VARCHAR | `omnifocus_task` / `mark_read` / `move` / `spam` / … |
| `action_payload` | JSONB | detaily akce |
| `status` | VARCHAR | `pending` / `executed` / `failed` / `cancelled` |
| `confirmed_by` | VARCHAR | kdo potvrdil (telegram/auto) |
| `confirmed_at` | TIMESTAMPTZ | |
| `executed_at` | TIMESTAMPTZ | |
| `result` | JSONB | výsledek provedení |
| `created_at` | TIMESTAMPTZ | |

Indexy: `(source_type, source_id)`, `status`

**Stav 2026-04-25:** Tabulka **prázdná, kód do ní nezapisuje**. Rezervována pro budoucí confirmation workflow (pending → confirmed → executed). Aktuální logging akcí běží v ChromaDB (viz dále).

---

### ChromaDB — collection `email_actions`

| Field | Popis |
|---|---|
| `id` | `email_messages.id` (UUID jako string) |
| `embedding` | vektor z Ollama `nomic-embed-text` (cosine space) |
| `document` | `"<from_address> <subject> <body[:400]>"` |
| `metadata.action` | `mark_read` / `hotovo` / `precteno` / `spam` / `unsub` / `of` / `rem` / `note` / `ceka` |
| `metadata.typ` | klasifikace (NEWSLETTER, FAKTURA, …) |
| `metadata.firma` | klasifikace |
| `metadata.mailbox` | email adresa účtu |

**Použití:**
- `store_email_action()` po každé akci (auto / TG / WebUI)
- `find_repeat_action()` před TG notifikací — pokud najde ≥3 podobné s cosine ≤0.15 a stejnou akcí → automatická exekuce, žádná TG zpráva
- Konstanty: `AUTO_THRESHOLD_COUNT=3`, `AUTO_THRESHOLD_DIST=0.15`

---

### `claude_sender_verdicts` (2026-04-25)

Cache výsledků Claude verifikace spamu — jeden záznam na odesílatele.

| Sloupec | Typ | Popis |
|---|---|---|
| `email` | TEXT PK | čistá emailová adresa (bez display name) |
| `is_spam` | BOOLEAN | verdikt Claude |
| `reason` | TEXT | 1 věta vysvětlení |
| `verified_at` | TIMESTAMP | kdy verifikováno |

**Použití:** `_claude_verify_spam()` v `classify_emails.py` — nejdřív zkontroluje cache, API volá jen při cache miss. UPSERT při opakovaném volání (přepíše starý verdikt).

---

### `attachments` (migrace — existuje v DB)

Reference na soubory příloh emailů uložených na disku.

| Sloupec | Typ | Popis |
|---|---|---|
| `id` | UUID PK | |
| `source_type` | VARCHAR | `email` |
| `source_record_id` | UUID | FK → `email_messages.id` (::uuid cast nutný v dotazu) |
| `filename` | VARCHAR | bezpečný název souboru |
| `file_path` | TEXT | cesta v kontejneru (`/app/attachments/...`) |
| `mac_path` | TEXT | cesta na Mac hostu (`/Users/pavel/Desktop/OmniFocus/...`) |
| `content_type` | VARCHAR | MIME type |
| `size_bytes` | BIGINT | velikost |
| `saved_at` | TIMESTAMPTZ | |

**Bind mount:** `/Users/pavel/Desktop/OmniFocus:/app/attachments` — scheduler zapisuje, Apple Bridge čte přes mac_path.

---

### `classification_rules` (migrace 008)

| Sloupec | Typ | Popis |
|---|---|---|
| `id` | SERIAL PK | |
| `rule_type` | VARCHAR | `spam` / `firma` / `typ` |
| `match_field` | VARCHAR | `from_address` / `subject_contains` / `domain` |
| `match_value` | VARCHAR | hodnota pro shodu |
| `result_value` | VARCHAR | výsledná klasifikace |
| `confidence` | FLOAT | jistota (default 1.0) |
| `hit_count` | INT | kolikrát pravidlo zasáhlo (default 1) |
| `created_at` | TIMESTAMPTZ | |
| `updated_at` | TIMESTAMPTZ | |

UNIQUE constraint: `(rule_type, match_field, match_value)`

---

### `topics` (migrace 009)

| Sloupec | Typ | Popis |
|---|---|---|
| `id` | SERIAL PK | |
| `name` | VARCHAR | název tématu |
| `parent_id` | INTEGER FK | nadřazené téma (NULL = hlavní téma) |
| `priority` | VARCHAR | `high` / `medium` / `low` |
| `description` | TEXT | popis pro AI kontext |
| `created_at` | TIMESTAMPTZ | |

Poznámka: `parent_id` má ON DELETE CASCADE.

---

### `topic_signals` (migrace 009)

| Sloupec | Typ | Popis |
|---|---|---|
| `id` | SERIAL PK | |
| `topic_id` | INTEGER FK | vazba na `topics` |
| `signal_type` | VARCHAR | `positive` / `negative` / `brand` / `system` / `compatible` |
| `value` | VARCHAR | keyword pro LIKE matching |

Pravidla:
- Název tématu NENÍ automaticky signál — musí být explicitně přidán
- Signály kratší než 4 znaky způsobují false positives — LIKE `%PSI%` zasáhne i jiná slova
- Scoring: `SELECT DISTINCT ON (v.id, t.id) COUNT(*) AS score FROM youtube_videos v CROSS JOIN topics t JOIN topic_signals s ON s.topic_id = t.id WHERE v.title ILIKE '%' || s.value || '%'`

---

### `topic_intersections` (migrace 009)

| Sloupec | Typ | Popis |
|---|---|---|
| `id` | SERIAL PK | |
| `topic_a_id` | INTEGER FK | první téma |
| `topic_b_id` | INTEGER FK | druhé téma |
| `relevance` | TEXT | popis průniku |
| `score` | FLOAT | váha průniku (default 1.0) |

---

### `config` (migrace 001)

| key | value | module |
|---|---|---|
| `email.retention_days` | 730 | email |
| `rss.retention_days` | 30 | rss |
| `mantis.escalation_days` | 7 | mantis |
| `youtube.retention_days` | 90 | youtube |
| `dedup.email.strategy` | message_id | email |
| `dedup.rss.strategy` | url_hash | rss |

---

### `imap_status` (migrace 010)

Per-account IMAP IDLE health — zobrazeno v dashboardu.

| Sloupec | Typ | Popis |
|---|---|---|
| `mailbox` | VARCHAR PK | emailová adresa účtu |
| `status` | VARCHAR | `idle` / `connecting` / `error` |
| `last_seen` | TIMESTAMPTZ | poslední úspěšná aktivita |
| `last_error` | TEXT | poslední chyba (transient/permanent) |
| `updated_at` | TIMESTAMPTZ | |

---

### `sources`, `sessions`, `attachments` (migrace 001)

Sdílené systémové tabulky — viz `sql/001_init.sql`.

---

## Apple Bridge — endpointy

FastAPI na hostu, port 9100, autostart přes launchd.

| Metoda | Endpoint | Popis |
|---|---|---|
| GET | `/health` | status check |
| GET | `/omnifocus/tasks` | aktivní tasky (bulk JXA fetch) |
| GET | `/omnifocus/projects` | seznam projektů |
| POST | `/omnifocus/add_task` | přidá task do OmniFocus inboxu |
| GET | `/imessage/recent?limit=50` | posledních N iMessage zpráv (sqlite) |
| GET | `/notes/all` | všechny Apple Notes |
| GET | `/reminders/all` | nedokončené Reminders ze všech seznamů |
| GET | `/contacts/all` | kontakty ze sqlite AddressBook |
| GET | `/calendar/events?days=60` | události z iCloud Calendar přes CalDAV |

**POST /omnifocus/add_task body:**
```json
{"name": "název tasku", "note": "poznámka", "flagged": true}
```

**Restart:**
```bash
launchctl unload ~/Library/LaunchAgents/cz.brogiasist.apple-bridge.plist
launchctl load   ~/Library/LaunchAgents/cz.brogiasist.apple-bridge.plist
```

---

## Email klasifikační pipeline

```
Nový email (IMAP IDLE push)
  │
  ▼
email_messages INSERT (status='new') + přílohy → attachments tabulka + disk
  │
  ▼ classify_emails.py (každých 5 min)
1. classification_rules — from_address shoda (manuální pravidla; spam → trash, continue)
2a. POZVÁNKA pravidlo — subject ILIKE 'Invitation:%' → typ=POZVÁNKA, bez Llamy, continue
2b. apple_contacts whitelist — in_contacts=True → blokuje AI spam (pravidla ho přepíší)
3. Llama3.2 → JSON: firma, typ, task_status, is_spam, confidence, reason
4. Kontakt override: if in_contacts AND is_spam → is_spam=False
5. _save_classification (status='classified')
6. Spam handling:
   ├─ is_spam AND confidence ≥ 0.92 → move_to_trash + TG "🗑️ AUTO-SPAM (X%)"
   └─ is_spam AND confidence < 0.92 → _claude_verify_spam()
        ├─ cache hit (claude_sender_verdicts) → žádné API volání
        ├─ cache miss → Claude Haiku API → INSERT claude_sender_verdicts
        ├─ claude.is_spam=True → move_to_trash + TG "🗑️ AUTO-SPAM Claude [cache] (X%)"
        ├─ claude.is_spam=False → _save_classification(is_spam=False), normální průchod
        └─ claude=None (error) → send_spam_check (TG spam-check s tlačítky)
7. Auto-move: confidence ≥ 0.85 AND typ IN (NOTIFIKACE,NEWSLETTER,ESHOP,POTVRZENÍ,FAKTURA)
   → move_to_brogi_folder(<typ>)
  │
  ▼ notify_emails.py (každé 2 min)
SELECT WHERE typ IS NOT NULL AND is_spam=FALSE AND tg_notified_at IS NULL
  │
  ▼ Před TG zprávou: chroma_client.find_repeat_action(from, subject, body)
  │   → pokud match: provede akci automaticky (mark_read / hotovo / move / …)
  │   → store_email_action po akci + TG "🔁 Opakuji akci: X"
  │
  ▼ Pokud žádný pattern: pošli TG zprávu s inline tlačítky
→ nastav tg_notified_at=NOW(), tg_message_id=<msg_id>
  │
  ▼ telegram_callback.py (polling každé 2s — daemon thread)
Zpracuj kliknutí:
  hotovo   → move_to_brogi_folder(HOTOVO) + status='reviewed' + human_reviewed=TRUE
  precteno → move_to_brogi_folder(<typ>) + status='reviewed' + human_reviewed=TRUE
  ceka     → task_status='ČEKÁ-NA-MĚ', human_reviewed=TRUE (zůstává v INBOX)
  spam     → is_spam=TRUE + move_to_trash + INSERT classification_rules (from_address)
  of       → POST apple-bridge /omnifocus/add_task (flagged=TRUE, note=body_text[:1500]+přílohy) + move_to_brogi_folder(HOTOVO)
  rem      → POST apple-bridge /reminders/add + move_to_brogi_folder(HOTOVO)
  note     → POST apple-bridge /notes/add + move_to_brogi_folder(HOTOVO)
  cal      → POST apple-bridge /calendar/add + move_to_brogi_folder(HOTOVO)
  unsub    → is_spam=TRUE pro celý from_address + classification_rules INSERT + move_to_trash
  skip     → jen answer_callback, nic nemění
  │
  ▼ Po každé akci:
  • store_email_action() → ChromaDB (učení pro find_repeat_action)
  • delete_message(tg_message_id) → smaže TG zprávu s tlačítky
```

**Telegram callback formáty:**
- `email:hotovo:{id}`
- `email:precteno:{id}`
- `email:ceka:{id}`
- `email:spam:{id}`
- `email:of:{id}`
- `email:rem:{id}`
- `email:note:{id}`
- `email:cal:{id}`
- `email:unsub:{id}`
- `email:skip:{id}`
- `spam:yes:{id}` (legacy)
- `spam:no:{id}` (legacy)

---

## Topics / Signals — scoring obsahu

Keyword matching YouTube videí (a v budoucnu RSS, emailů) proti zájmovým tématům.

```
topic_signals (keyword seznam)
  │
  ▼ SQL CROSS JOIN + ILIKE '%keyword%'
  │  DISTINCT ON (video_id, topic_id)
  ▼ score = počet shod na téma
  │
  ▼ zobrazení na /obsah (seskupeno dle tématu, hierarchicky)
```

**Pravidla:**
- Název tématu NENÍ automaticky signál — musí být explicitně přidán jako `positive`
- Krátké signály (< 4 znaky) jsou nebezpečné — LIKE matching zasáhne false positives
- Signal typy: `positive` (chci), `negative` (nechci), `brand` (®), `system` (⚙), `compatible` (🔗)

---

## AI analýza — dvouvrstvá architektura

### Vrstva 1 — Deterministická pravidla
- Tabulka `classification_rules`
- Shoda na `from_address` / `subject_contains` / `domain`
- Žádné AI volání — okamžitý výsledek
- Učí se z Pavlových korekcí přes TG tlačítka (hit_count++)

### Vrstva 2 — Llama3.2 (lokální)
- Model: `llama3.2-vision:11b` přes Ollama
- URL: `http://host.docker.internal:11434`
- Nastupuje pokud vrstva 1 nemá pravidlo
- Výstup: JSON s `firma` / `typ` / `task_status` / `is_spam` / `confidence` / `reason`
- Auto-spam threshold: `confidence > 0.92` → označí bez TG notifikace

### Vrstva 3 — Claude Haiku (spam verifikace)
- Model: `claude-haiku-4-5` přes Anthropic API (httpx, bez SDK)
- URL: `https://api.anthropic.com/v1/messages`
- Nastupuje pokud Llama označí spam s `confidence < 0.92`
- **Cache**: `claude_sender_verdicts` — každý odesílatel verifikován max. jednou
- Výstup: `{"is_spam": bool, "reason": "1 věta"}`
- Fallback: pokud API selže → TG spam-check (neztrácíme email)

---

## Telegram bot

| Parametr | Hodnota |
|---|---|
| Token | `TELEGRAM_BOT_TOKEN` v `.env` |
| Chat ID | `TELEGRAM_CHAT_ID` v `.env` |
| Polling interval | 2s (`getUpdates`) — daemon thread v scheduleru |
| Notifikace job | každé 2 minuty (`notify_emails.py`) |
| Callback offset | globální `_offset` v `telegram_callback.py` |

---

## Scheduler — přehled jobů

| Job ID | Funkce | Interval | Popis |
|---|---|---|---|
| `imap_idle` | `imap_idle_loop()` | daemon | IMAP IDLE push pro 8 účtů |
| `imap_scan` | `scan_all_mailboxes()` | 30min | záložní scan všech schránek |
| `rss` | `ingest_rss()` | 30min | The Old Reader |
| `youtube` | `ingest_youtube()` | 2h | YouTube Data API |
| `mantis` | `ingest_mantis()` | 30min | MantisBT REST |
| `omnifocus` | `ingest_omnifocus()` | 10min | Apple Bridge JXA |
| `notes` | `ingest_notes()` | 30min | Apple Notes |
| `reminders` | `ingest_reminders()` | 15min | Apple Reminders |
| `contacts` | `ingest_contacts()` | 6h | Apple Contacts sqlite |
| `calendar` | `ingest_calendar()` | 15min | CalDAV iCloud |
| `classify` | `classify_emails()` | 5min | Llama + pravidla |
| `notify` | `notify_classified_emails()` | 2min | Telegram notifikace |
| `tg_callback` | `run_callback_loop()` | daemon | Telegram polling |

---

## Konfigurace — klíče v `.env`

| Proměnná | Popis |
|---|---|
| `POSTGRES_HOST/PORT/USER/PASSWORD/DB` | DB připojení |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token |
| `TELEGRAM_CHAT_ID` | Pavel's Telegram chat ID |
| `IMAP_*` | 8 emailových účtů (HOST, PORT, USER, PASSWORD, EMAIL) |
| `APPLE_BRIDGE_URL` | URL apple-bridge (default: `http://host.docker.internal:9100`) |
| `OLLAMA_URL` | Llama endpoint (default: `http://host.docker.internal:11434`) |
| `CHROMA_HOST/PORT` | ChromaDB |
| `YOUTUBE_CLIENT_ID/SECRET` | OAuth pro YouTube API |
| `ICLOUD_USER/PASSWORD` | CalDAV přístup (dxpavel@me.com) |

---

## Stav implementace

| Komponenta | Stav | Poznámka |
|---|---|---|
| IMAP ingest (8 účtů) | ✅ | IDLE push + 30min backup scan |
| RSS ingest | ✅ | The Old Reader |
| YouTube ingest | ✅ | OAuth, 2h interval |
| Mantis ingest | ✅ | REST API |
| OmniFocus ingest | ✅ | JXA bulk fetch, 10min |
| Apple Notes/Reminders/Contacts/Calendar | ✅ | Apple Bridge |
| Email klasifikace (pravidla + Llama) | ✅ | classify_emails.py |
| Telegram notifikace s inline tlačítky | ✅ | notify_emails.py |
| Telegram callback handler | ✅ | telegram_callback.py |
| Topics/signals systém | ✅ | DB + Admin WebUI /admin |
| YouTube scoring na /obsah | ✅ | SQL CROSS JOIN + LIKE |
| OF task přes apple-bridge | ✅ | endpoint funkční |
| IMAP akce (move, mark read) | ✅ | `imap_actions.py` — mark_read, move_to_trash, move_to_brogi_folder |
| Backfill skripty (retroaktivní akce) | ✅ | `backfill_imap.py`, `backfill_mark_read.py`, `backfill_spam_read.py` |
| ChromaDB action learning | ✅ | `store_email_action` + `find_repeat_action` (pattern → auto-akce) |
| ChromaDB WebUI `/chroma` | ✅ | čtení, inline edit, mazání vzorů |
| ChromaDB semantic search | ❌ | plánováno (mimo find_repeat_action zatím nepoužito) |
| Apple Contacts whitelist | ✅ | `_is_contact()` — odesílatel v kontaktech → nikdy auto-spam |
| POZVÁNKA deterministické pravidlo | ✅ | `subject ILIKE 'Invitation:%'` → bez Llamy |
| TG Unsub tlačítko | ✅ | přidáno do UNIVERSAL_BUTTONS |
| TG auto-spam notifikace | ✅ | `🗑️ AUTO-SPAM` při automatickém přesunu do koše |
| OF body_text + přílohy | ✅ | `body_text[:1500]` + `file://` linky v note |
| `actions` tabulka — confirmation workflow | ❌ | tabulka existuje, kód nepoužívá |
| iMessage ingest | ❌ | sqlite přístup znám, skript chybí |
| Claude API — spam verifikace | ✅ | `_claude_verify_spam()` + `claude_sender_verdicts` cache |
| Claude API — plná analýza | ❌ | plánováno |

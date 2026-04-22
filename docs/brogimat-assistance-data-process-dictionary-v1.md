---
Název: Datový a procesní slovník BrogiMatAssistance
Soubor: docs/brogimat-assistance-data-process-dictionary-v1.md
Verze: 2.0
Poslední aktualizace: 2026-04-22
Popis: Architektonická rozhodnutí, dataflow, DB invarianty, storage strategie
Změněno v: 2026-04-22 — vyplněno (dohodnutá architektura)
---

# Datový a procesní slovník — BrogiMatAssistance

---

## Universální dataflow (platí pro všechny moduly)

```
ZDROJ (IMAP / Mantis / RSS / YouTube / iMessage / ...)
  │
  ▼ INGEST
raw kopie → PostgreSQL (mirror)
  │
  ▼ ANALÝZA
AI + pravidla → rozhodnutí + návrh akcí
  │
  ▼ POTVRZENÍ
Pavel schválí (nebo odmítne)
  │
  ▼ EXECUTE
postproces na originále (odpovědět, označit, přesunout, smazat, ...)
  │
  ▼ LOG
action_log (kdo / kdy / co / výsledek)
```

**Klíčový princip:** Zdroj pravdy dat zůstává venku (IMAP, Mantis, Apple apps).
Naše DB je pracovní kopie pro rozhodovací vrstvu. Rozhodnutí a audit trail jsou v naší DB.

---

## Invarianty každé modulové tabulky

Každá tabulka ukládající data ze zdroje MUSÍ obsahovat:

| Sloupec | Typ | Popis |
|---|---|---|
| `id` | UUID / SERIAL | interní PK |
| `source_type` | VARCHAR | typ zdroje: `email`, `mantis`, `rss`, `imessage`, ... |
| `source_id` | VARCHAR | ID z externího zdroje (message-id, mantis issue id, URL hash...) |
| `raw_payload` | JSONB | kompletní raw kopie ze zdroje (nic se nevyhazuje) |
| `ingested_at` | TIMESTAMPTZ | kdy jsme stáhli |
| `status` | VARCHAR | stav zpracování: `new` / `analyzed` / `pending_confirm` / `executed` / `ignored` |
| `processed_at` | TIMESTAMPTZ | kdy proběhlo zpracování (NULL = nové) |

---

## Strategie: Mirror + Action log

- **Mirror vždy** — raw data ze zdroje se vždy kopírují do PG. Mirror je základní podmínka pro analýzu a vektorizaci.
- **Action log vždy** — každá akce (nejen úspěšná) se zapisuje do sdílené tabulky `actions`. Nikdy per-modul.
- Toto jsou **povinná pravidla**, ne volitelná.

---

## Tabulka `actions` (action log) — sdílená

| Sloupec | Typ | Popis |
|---|---|---|
| `id` | UUID | PK |
| `source_type` | VARCHAR | z jakého modulu (email, mantis, ...) |
| `source_id` | VARCHAR | na jaký záznam se akce váže |
| `action_type` | VARCHAR | typ akce: `reply`, `mark_read`, `move`, `delete`, `create_issue`, `add_note`, ... |
| `action_payload` | JSONB | detaily akce (komu, co, parametry) |
| `status` | VARCHAR | `pending` / `executed` / `failed` / `cancelled` |
| `confirmed_by` | VARCHAR | kdo potvrdil (pavel / auto) |
| `confirmed_at` | TIMESTAMPTZ | kdy potvrzeno |
| `executed_at` | TIMESTAMPTZ | kdy provedeno |
| `result` | JSONB | výsledek exekuce (response kód, error message...) |
| `created_at` | TIMESTAMPTZ | kdy záznam vznikl |

---

## Tabulka `sessions` (session paměť — plán)

| Sloupec | Typ | Popis |
|---|---|---|
| `id` | VARCHAR | session ID (ses_xxxxx) |
| `status` | VARCHAR | `active` / `closed` |
| `created_at` | TIMESTAMPTZ | |
| `last_activity_at` | TIMESTAMPTZ | |
| `expires_at` | TIMESTAMPTZ | auto-expiry |

Expiry: max interakcí / timeout 30 min / Pavel explicitně zavře.
Detaily: viz `brogimat-assistance-system-popis-v1.md`.

---

## Tabulka `config` — parametry v DB

Retence, deduplikace kritéria a konfigurace zdrojů jsou v DB, ne hardcoded ani v .env.

Struktura per modul (příklady):

| Klíč | Hodnota | Modul |
|---|---|---|
| `email.retention_days` | 730 | Email |
| `rss.retention_days` | 30 | RSS |
| `mantis.escalation_days` | 7 | Mantis |
| `dedup.email.strategy` | `message_id` | Email |
| `dedup.rss.strategy` | `url_hash` | RSS |

Deduplication: patterny a duplicity hledá AI — pravidla vznikají učením, ne návrhem předem.

---

## Tabulka `sources` — konfigurace zdrojů

Mailboxy, RSS kanály, Mantis endpointy, YouTube kanály — vše konfigurovatelné přes DB.
Sdílená struktura s budoucími projekty.

| Sloupec | Typ | Popis |
|---|---|---|
| `id` | UUID | PK |
| `source_type` | VARCHAR | `imap`, `mantis`, `rss`, `youtube`, `imessage` |
| `name` | VARCHAR | popis (např. "brogi@dxpsolutions.cz") |
| `config` | JSONB | connection params (host, port, user, ...) |
| `active` | BOOLEAN | zapnuto/vypnuto |
| `created_at` | TIMESTAMPTZ | |

Credentials se neukládají plain text — viz `brogimat-assistance-credentials-v1.md`.

---

## Přílohy

- Fyzicky uloženy na **Synology mount** (PROD) / lokální disk (DEV)
- Cesta v DB konfiguraci (`config` tabulka), ne hardcoded
- Reference z modulových tabulek přes tabulku `attachments`

| Sloupec | Typ | Popis |
|---|---|---|
| `id` | UUID | PK |
| `source_type` | VARCHAR | z jakého modulu |
| `source_record_id` | UUID | FK na parent záznam |
| `filename` | VARCHAR | původní název |
| `storage_path` | VARCHAR | cesta na disku (relativní k mount pointu) |
| `mime_type` | VARCHAR | |
| `size_bytes` | INTEGER | |
| `ingested_at` | TIMESTAMPTZ | |

---

## Vektorizace (ChromaDB)

- Vektorizuje se **celý obsah** + **přílohy** (text extrahovaný z PDF, DOCX apod.)
- Data model ChromaDB kolekcí navrhuje AI postupně podle reálných dat
- Embeddings: TBD (volba modelu při implementaci)
- Sdílená ChromaDB instance — kolekce per modul (prefix: `brogi_email_`, `brogi_mantis_`, ...)

---

## Rozhodnutí a stav implementace

| Téma | Rozhodnutí | Status |
|---|---|---|
| Migration tool | Raw SQL — číslované soubory v `sql/` | ✅ 2026-04-22 |
| Docker stack | PostgreSQL 16 + ChromaDB (docker-compose.yml) | ✅ 2026-04-22 |
| PG port DEV | 5433 (5432 obsazen lokálním PG) | ✅ |
| DB schéma | 001_init.sql + 002_email.sql | ✅ 2026-04-22 |
| ChromaDB API | v2 (`/api/v2/`) | ✅ |
| iCloud IMAP | App-specific password — dxpavel / oqjf-qiul-pmiw-eoib | ✅ |
| Ingest engine | TBD — Python worker (nejpravděpodobnější) | ⏳ |
| Embeddings model | TBD při implementaci ChromaDB kolekcí | ⏳ |
| Přílohy — cesta | TBD — konfigurováno přes `config` tabulku | ⏳ |
| iMessage | PROD only — webhook Mac Studio | ⏳ |

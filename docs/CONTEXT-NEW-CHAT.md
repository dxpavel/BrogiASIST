---
Název: CONTEXT-NEW-CHAT
Soubor: docs/CONTEXT-NEW-CHAT.md
Verze: 8.3 (M1 final + BUG-010 FIXED — Zero open BUGs)
Poslední aktualizace: 2026-05-04 (pozdní noc)
Popis: Kontext pro nový chat — stav, cesty, problémy
---

# CONTEXT-NEW-CHAT — BrogiASIST

> **POZOR:** Aktivní implementace je na **branch `2`** (release v2 — Email Semantics v1 + M-features).
> Last commit: `084992b` (Merge: M2/M3/M4/M5-pre + spec, 2026-05-04).
> Pro detailní handoff viz `docs/SESSION-HANDOFF-D-CONTINUATION.md` (v2.0, UPDATE 2026-05-04 večer).
> Pro M5 plán: `docs/feature-specs/FEATURE-AI-CASCADE-v1.md` (v1.1).
> Stable bod návratu: tag `v1.1` (commit `ee483ba` na main).

## Co je nově HOTOVO (2026-05-04 evening + late-evening session)

**Evening:**
- **M3** STATUS kolečka v dashboard email tabulce
- **M4** Decision Engine editor v `/pravidla` — CRUD + filter chips + drag&drop priority + inline edit
- **M2** 2undo TTL 1h pro 8 reverzibilních akcí + ↶ Vrátit (1h) button v TG
- **M5-pre** subject/body keyword condition_types v decision_rules (engine + UI)
- **BUG-013** Llama confidence sanitize FIXED+DEPLOYED
- **BUG-014** mark_read skip Trash FIXED+DEPLOYED
- **Apple Bridge** rozšířen: 3 DELETE endpointy + ID v add response
- **Migrace 016** aplikovaná na PROD: 5 nových sloupců v email_messages

**Late-evening:**
- **M5 session 2** Llama threshold tracking (`CLAUDE_VERIFY_THRESHOLD` env) + `/admin` AI Source tile widget
- **BUG-001** email_actions.py refactor (909→110 ř.)
- **L5** tag **v2.0** + merge `2`→main
- **L1** Email Semantics v1 status (NOVÝ/ZPRACOVANÝ/SMAZANÝ + migrace 018)
- **L2** smazat sqlite contacts endpoint v Bridge
- **Migrace 017** ai_source + **018** status_semantics na PROD

**Night:**
- **BUG-004/005** FIXED — per-host BrogiASIST path + `_uid_move` raise
- **BUG-006** FIXED — audit 34 PROD emailů, 32 flagged `imap_lost=TRUE`
- **BUG-010 prep** — `X-Brogi-Auto` header v ingest, full M1 v další session
- **Migrace 019** `imap_lost`

**Late night — M1 final + BUG-010 FIXED:**
- **`smtp_send.py`** modul — SMTP klient s SMTP_MAP/SENT_MAP per provider
- **5/5 SMTP probe OK** (Gmail/iCloud/Forpsi/Synology/Seznam)
- **Akce `thanks`** — deterministický „Díky" reply
- **Akce `reply`** — TG text-input state machine (migrace 020 `tg_pending_replies`)
- **Akce `cal_accept`** — POZVÁNKA: CAL event + text reply pozvateli
- **TG buttony**: DOKLAD/INFO/.../FAKTURA pre-row `[✉️ 2thanks] [✏️ 2reply]`,
  POZVÁNKA pre-row `[📅✉️ 2cal+Accept]`
- **Migrace 020** `tg_pending_replies` (chat_id PK, TTL 30min)
- **🎉 Zero open BUGs.**

## Příští session = M5 session 2 (Llama refinement)

Spec: `docs/feature-specs/FEATURE-AI-CASCADE-v1.md` sekce 3 + 8.
Lessons relevantní: #45 (numeric sanitize), #46 (IMAP UID po MOVE), #47 (audit endpointů), #48 (spec před implementací).

---

## Co projekt je
Osobní asistent pro Pavla — přebírá operativu (emaily, OmniFocus, iMessage,
Mantis, rutiny). Pavel potvrzuje rozhodnutí, asistent vykonává.
Cíl: z 1-2h operativy denně na 10-15 minut.

---

## Aktuální stav (2026-04-27)

### Co bylo dnes uděláno (2026-04-27 session)
- **H1 / BUG-009** ✅ — JXA `/contacts/all` vrací emails+phones, datasety sjednocené (1181 řádků, 512 s email∩groups)
- **H3** ✅ — decision_engine flagy persistují do `email_messages` (sql/015), visual indikátory v TG (⭐ VIP, 👤 personal, 👥 GROUPS), `no_auto_action` blokuje auto-trash spam
- **BUG-011** ✅ — case-insensitive email match v group rules (jsonb_array_elements + LOWER())
- **H2** ✅ — Bridge `add_task` vrací task_id, callback persistuje of_task_id, threading detekce + speciální TG zpráva s 4 buttony (📂/📎/➕/⏭)
- **Backfill** 70 historických emailů → 4 dostaly `is_personal=true`



### PROD běží na VM 103 (10.55.2.231) — 5 kontejnerů + Apple Bridge
- **VM 103 (Proxmox)** — Ubuntu 24.04, brogiasist Docker stack:
  - PostgreSQL 16 (port 5432, container `brogiasist-postgres`)
  - ChromaDB (port 8000, container `brogiasist-chromadb`)
  - Ollama (port 11434, container `brogiasist-ollama`, model `llama3.2-vision:11b`)
  - Dashboard FastAPI + Jinja2 (port 9000, container `brogiasist-dashboard`)
  - Scheduler APScheduler + IMAP IDLE + Telegram (port 9001, container `brogiasist-scheduler`)
- **PajaAppleStudio (10.55.2.117)** — Apple Bridge FastAPI:
  - Python 3.11.15 (Homebrew) přes launchd, port 9100
  - **BUG-008 fix:** `os.posix_spawn()` místo `subprocess.run()` (multi-threaded fork bug)
  - **TCC FDA toggle** v System Settings nutný pro `/contacts/all_sqlite` (legacy fallback) — JXA `/contacts/all` (primary) FDA nepotřebuje, používá AppleEvents
- **Telegram bot** (polling loop v scheduleru, callback handler aktivní, offset v `config` tabulce)

### Co je implementováno

**Ingest:**
- IMAP ingest (9 účtů, IDLE push + 30min backup scan)
- RSS ingest (The Old Reader, 30min)
- YouTube ingest (OAuth, 2h)
- MantisBT ingest (30min)
- OmniFocus ingest (Apple Bridge JXA, 10min)
- Apple Notes ingest (30min)
- Apple Reminders ingest (15min)
- Apple Contacts ingest (JXA, **12h, hash check, vrací groups**)
- Calendar ingest (AppleScript, 15min)

**Klasifikace + akce (v2 — branch `2`):**
- **decision_rules engine** (`decision_engine.py`, 9 pravidel v DB) — runs PŘED Llamou:
  - header_list (List-Id → TYP=LIST), header_encrypted, header_oof (OOO), header_bounce
  - group_vip / sender_personal (z apple_contacts.groups) — **FUNGUJE od 2026-04-27, BUG-009+BUG-011 fixed**
  - chroma_match (cosine < 0.15), self_sent (X-Brogi-Auto), ai_fallback
- **Llama3.2 prompt** vrací 6 TYPů: ÚKOL, DOKLAD, NABÍDKA, NOTIFIKACE, POZVÁNKA, INFO (ERROR/LIST/ENCRYPTED detekuje engine pre-AI)
- **Per-TYP TG tlačítka** dle spec sekce 7 (`notify_emails.py:_buttons_for_typ()`)
- **Pending queue worker** (`pending_worker.py`) — degraded mode pro Apple Bridge offline:
  - Bridge unreachable → enqueue do `pending_actions` (místo ztráty akce)
  - Drain worker (interval 1 min, throttle 2s) → opakuje akce po obnově Bridge

**Telegram:**
- Notifikace klasifikované emaily s inline tlačítky (per TYP, 2min interval)
- Callback handler: hotovo/přečteno/čeká/spam/of/rem/note/unsub/skip
- Po každé akci se smaže TG zpráva (`delete_message`)
- Offset persistentní v `config` tabulce — callbacks přežijí restart scheduleru

**Apple Bridge endpointy (vč. nové z 2026-04-26):**
- GET `/health`, `/omnifocus/tasks`, `/omnifocus/projects`, `/notes/all`, `/calendar/events`
- POST `/omnifocus/add_task`, `/notes/add`, `/reminders/add`, `/calendar/add`
- **GET `/contacts/all`** (JXA s groups, hash check)
- **GET `/omnifocus/task/{id}`**, **POST `/omnifocus/task/{id}/append_note`**
- **GET `/notes/{id}`**, **POST `/notes/{id}/append`**
- TODO: `/calendar/reply`, `/mail/send` (BUG-010 — Mail.app neumí custom headers)

**Dashboard WebUI:**
- Index, pravidla, úkoly, obsah, admin, chroma
- Email tabulka: `.typ-box` kostičky s TYP barvami (sekce 19 spec)
- Filter chips: 9 nových TYPů (ÚKOL/DOKLAD/NABÍDKA/NOTIFIKACE/POZVÁNKA/INFO/ERROR/LIST/ENCRYPTED)
- CSS variables pro grafickou semantiku (kostičky/fill/kazeťák kolečka)
- **CLS fix:** `display=optional` na Google Fonts + img dimensions
- Apple Bridge + DB + ChromaDB status na dashboard
- Topics/signals systém + YouTube scoring proti tématům
- Classification rules + decision_rules tabulky (zatím SQL only, WebUI editor TODO M4)

**IMAP akce:** `imap_actions.py` — mark_read, move_to_trash, move_to_brogi_folder

**Action logging:** ChromaDB collection `email_actions` (NE PG `actions` tabulka)

### Co chybí / TODO

**HIGH (před produkcí v2 — viz SESSION-HANDOFF-D-CONTINUATION.md):**
- **BUG-009: Group matching disjoint dataset** — 1180 starých kontaktů má emails ale ne groups, 1180 nových má groups ale ne emails → SQL JOIN nematchne nikdy. Fix: rozšířit JXA o emails (pomalejší ingest) + smazat starý dataset.
- **D5+ Threading TG flow** — endpointy ready, chybí callback handlers (`of_open`, `of_append`) v `telegram_callback.py` + detekce v `notify_emails.py`.
- **D2 action wiring** — flagy z decision_rules (`is_personal`, `force_tg_notify`, `no_auto_action`) zatím ignorujeme.

**MEDIUM:**
- **BUG-010: D3+ /calendar/reply + /mail/send** — Mail.app AppleScript neumí custom headers → X-Brogi-Auto subject marker workaround
- 2undo akce (TTL 1h)
- STATUS kolečko v email tabulce (CSS ready, jen Jinja apply)
- WebUI editor decision_rules

**LOW:**
- iMessage ingest (sqlite přístup znám, skript chybí)
- Topic intersections UI
- classification refactor na novou STATUS semantiku
- Multi-action (1 email → víc akcí)
- Merge branch `2` → main + tag `v2.0`

### Action logging — kde se loguje (pozor!)
- **NE** v PostgreSQL `actions` tabulce (prázdná, rezervovaná pro budoucí workflow)
- **ANO** v ChromaDB collection `email_actions` přes `chroma_client.store_email_action()` — embedding (Ollama nomic-embed-text) + metadata (action/typ/firma/mailbox/human_corrected/timestamp)
- Volá se po každé akci v `telegram_callback.py` a `api.py` (WebUI proxy); metadatata zahrnují kdo/kdy/co/proč/z jakého účtu
- Před TG notifikací: `find_repeat_action()` zkontroluje pattern (≥3 podobné s cosine ≤0.15 → auto-akce bez TG dotazu)
- Backfill 120 historických akcí z DB do ChromaDB: `services/ingest/backfill_chroma.py`

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

## Aktivní komponenty (PROD VM 103 + Apple Studio)

| Komponenta | Stav | Kde běží |
|---|---|---|
| PostgreSQL 16 | ✅ běží | Docker `brogiasist-postgres` (VM 103, port 5432) |
| ChromaDB | ✅ běží | Docker `brogiasist-chromadb` (VM 103, port 8000) |
| Ollama (llama3.2-vision:11b) | ✅ běží | Docker `brogiasist-ollama` (VM 103, port 11434) |
| Dashboard :9000 | ✅ běží | Docker `brogiasist-dashboard` (VM 103) |
| Scheduler / IDLE / TG | ✅ běží | Docker `brogiasist-scheduler` (VM 103, port 9001) |
| Pending queue worker | ✅ běží | součást scheduleru, interval 1 min |
| Apple Bridge :9100 | ✅ běží | Apple Studio (10.55.2.117, launchd, posix_spawn fix) |
| Llama klasifikace | ✅ běží | Ollama v Dockeru |
| Decision rules engine | ✅ aktivní | součást classify_emails (PŘED Llamou) |

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
- Offset persistentní v `config` tabulce (key=`tg_callback_offset`) — callbacks přežijí restart scheduleru

---

## Topics / Signals systém

- Tabulky: `topics`, `topic_signals`, `topic_intersections`
- Admin WebUI: `/admin`
- Scoring YouTube: `/obsah` — SQL CROSS JOIN s LIKE matching
- Signal typy: positive, negative, brand, system, compatible
- Pravidlo: název tématu = NENÍ automaticky signál — musí být explicitně přidán

---

## Email klasifikace (v2 — branch `2`)

**TYPy** (per spec brogiasist-semantics-v1):
- ÚKOL, DOKLAD, NABÍDKA, NOTIFIKACE, POZVÁNKA, INFO (Llama klasifikuje)
- ERROR, LIST, ENCRYPTED (decision_rules engine — header check PŘED Llamou)
- Legacy v DB stále: FAKTURA, NEWSLETTER, POTVRZENÍ, ESHOP, SPAM (mapping na nové)

**Firmy:** DXPSOLUTIONS, MBANK, ZAMECNICTVI, PRIVATE, JOBS, JIMSOFT, PPDX_NET, ...

**Pipeline:**
1. **Header check** (decision_rules priority 5–40) — self_sent, header_list, header_encrypted, header_oof, header_bounce
2. **Skupina** (priority 50, 70) — group_vip, sender_personal *(BUG-009 disjoint data)*
3. **Chroma vzor** (priority 60) — cosine < 0.15 → apply_remembered_action
4. **AI fallback** (priority 80) — Llama klasifikace
5. **Auto-action threshold:** spam ≥ 92 %, konstruktivní ≥ 85 %, manuální 2unsub/2hotovo/2skip/2del

**Decision rules engine:** `services/ingest/decision_engine.py`, tabulka `decision_rules` (9 default pravidel)

**Llama model:** `llama3.2-vision:11b` přes Ollama (env: `OLLAMA_URL=http://ollama:11434`)
**Body limit:** 500 znaků (po HTML strip — TODO)

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
| spam / del / unsub | Trash (dle providera) |

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
| 2026-04-25 | Action logging definitivně přes ChromaDB `email_actions` (ne PG `actions`) — metadata: kdo/kdy/co/proč/z jakého účtu |
| 2026-04-25 | Backfill 120 historických email akcí z DB do ChromaDB (`backfill_chroma.py`) |
| 2026-04-25 | TG: Univerzální sada 8 tlačítek pro každý email (nezávisle na AI-typu); CHROMA_HOST opraven z localhost na chromadb |
| 2026-04-25 | TG offset persistentní v config tabulce — callbacks přežijí restart scheduleru |
| 2026-04-25 | KRITICKÁ OPRAVA: DB lock contention v `_email_action` — pořadí: bridge call → DB COMMIT → IMAP (nikdy IMAP před COMMIT) |
| 2026-04-25 | E2E verifikace: klik na TG tlačítko → rozhodnutí uloženo do DB + ChromaDB + IMAP přesun + TG zpráva zmizí |
| 2026-04-25 | Docker: scheduler nemá bind mount — změny kódu vyžadují `docker cp` + restart nebo rebuild image |
| 2026-04-26 | **PROD migrace na VM 103** (Proxmox) + Apple Bridge na Apple Studio |
| 2026-04-26 | **Email Semantics v1 spec** schválena — 9 TYPů, 5 STATUS, 8 ACTION + 2undo, prefix `2` = „to" (`docs/brogiasist-semantics-v1.md`) |
| 2026-04-27 | **Přidána ACTION `2del`** (univerzální „rychle smazat" tlačítko) — Trash + Chroma log, ALE žádný zápis do `classification_rules` (sender se neoznačí jako spam). Pro duplicity / šum, kdy 2spam by zbytečně označil odesílatele. Tlačítko ve **všech** TYPech (var. C). Nyní 9 ACTION + 2undo. |
| 2026-04-26 | **BUG-008 Apple Bridge fork() crash FIXED** — `os.posix_spawn()` místo `subprocess.run()` (workaround #1 OBJC env var na macOS 26.4 nefunguje) |
| 2026-04-26 | **Branch `2` rozjeta** — implementace v2: A (RFC headers), B (Apple Contacts groups), C (decision_rules engine), D1 (schema + threading), D2 (Llama prompt + per-TYP TG tlačítka), D4 (CLS fix + grafická spec), D5 (queue worker), D3 (4/6 endpointů) |
| 2026-04-26 | Tag `v1.1` (commit `ee483ba`) — bod návratu před implementací v2 |
| 2026-04-26 | **Pavlovo rozhodnutí:** existující 25 emailů a 2360 kontaktů NEMIGRUJEME — pouze nové prochází novou semantikou |
| 2026-04-26 | Group rules v decision_rules zatím nematchují — viz BUG-009 (data ve 2 disjoint datasets) |

---

## Lessons learned
→ Viz `docs/brogiasist-lessons-learned-v1.md` (sekce 35–37 jsou nové z 2026-04-26)

## Handoff pro pokračování
→ Viz `docs/SESSION-HANDOFF-D-CONTINUATION.md` (HIGH/MEDIUM/LOW priority + první krok zítra)

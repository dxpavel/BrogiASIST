---
Název: SESSION-HANDOFF-D-CONTINUATION
Soubor: docs/SESSION-HANDOFF-D-CONTINUATION.md
Verze: 2.0
Vytvořeno: 2026-04-26 22:30
Aktualizováno: 2026-05-04 (drift fix)
Popis: Handoff pro pokračování blockeru D z branch `2`.
       Status po session 2026-04-27: H1 ✅, H3 ✅, H2 ✅, BUG-009 ✅, BUG-011 ✅.
       Update 2026-05-04: PROD scheduler rebuild + DEV stop (drift kontejneru / TG 409 Conflict).
       Zbývá: M1–M4 (calendar/reply, 2undo, STATUS column, WebUI rules editor)
       + D3 zbylé 2 endpointy (mail/send, calendar/reply — vyžaduje rozhodnutí
       o headers, viz BUG-010) + L1–L5 vychytávky.
---

# BrogiASIST — Session Handoff (D continuation, v2.0)

## ⚠️ UPDATE 2026-05-04 (večer) — M2/M3/M4 hotové + M5 spec

**HOTOVO** (PROD deployed ~18:29 lokálně, branch `2`, merge commit `084992b`):
- **M3** STATUS kolečka v dashboard email tabulce (5 stavů: novy/precteny/cekajici/zpracovany/smazany)
- **M4** Decision Engine editor v `/pravidla` (CRUD + filter chips + drag&drop priority + inline edit)
- **M2** 2undo TTL 1h pro 8 reverzibilních akcí (`hotovo/precteno/ceka/spam/del/of/rem/cal`) + `↶ Vrátit (1h)` button v TG po akci
- **M5-pre** subject/body keyword condition_types v decision_rules (commit bc22501)
- **BUG-013** (Llama confidence sanitize) + **BUG-014** (mark_read skip Trash) FIXED+DEPLOYED

**Apple Bridge na 10.55.2.117** rozšířen:
- 3 nové DELETE endpointy (`/omnifocus/task/{id}`, `/reminders/{id}`, `/calendar/{event_uid}`)
- `/reminders/add` a `/calendar/add` vrací `id` v response (potřeba pro undo)

**Migrace 016_undo_history.sql** aplikovaná na PROD (5 nových sloupců: last_action, last_action_at, last_action_payload jsonb, rem_event_id, cal_event_id + partial index).

**M5 spec hotový:** `docs/feature-specs/FEATURE-AI-CASCADE-v1.md` (422 řádků, v1.1) — 3-vrstvý cascade pro 2 následující sessions.

**Příští session = M5 session 2 (Llama refinement):**
- threshold escalation logic (`CLAUDE_VERIFY_THRESHOLD` env, default 0.90)
- Llama prompt refinement (lessons #42 + #45 + few-shot příklady)
- subject/body Llama integration s M5-pre engine pravidly
- Spec: sekce 3 + 8 v `FEATURE-AI-CASCADE-v1.md`

---

## ⚠️ UPDATE 2026-05-04 — drift fix (krátká session)

**Příznak (Pavel):** některé TG zprávy po klasifikaci mají starou per-TYP sadu tlačítek místo nové univerzální 3×3 sady (vč. suggestion buttonu z `2837dae` + H2/H3 buttons).

**Root cause:**
1. PROD `brogiasist-scheduler` na VM 103 běžel od 2026-04-27 19:30 (6 dní). Mezitím 4 commity měnily `notify_emails.py` / callback / classify. Soubor v kontejneru byl aktualizovaný (md5 match s lokálem) — ale **Python process si naimportoval starý kód do paměti při startu**, `docker cp` bez restartu = no-op.
2. Paralelně **DEV `brogi-scheduler` na MacBooku** Pavla běžel ~2 hodiny → TG `getUpdates: 409 Conflict` → callbacky se rozdělily mezi PROD (nový kód) a DEV (starý kód) náhodně.

**Fix:**
- VM 103: `cd ~/brogiasist && docker compose up -d --build scheduler` (full rebuild).
- MacBook: `docker stop brogi-scheduler` (DEV stack zbytek běží).
- Verifikace: posledních 5 `getUpdates` → `200 OK`, žádný 409. Pavel potvrdil že nové TG zprávy mají správný layout.

**Stav PROD po fixu:**
- `brogiasist-scheduler` started 2026-05-04 08:43:38 (image rebuild)
- Všechny 4 klíčové moduly md5 OK (`notify_emails`, `telegram_callback`, `classify_emails`, `decision_engine`)
- TG bot konzumuje pouze PROD instance.

**Důsledky:**
- Staré TG zprávy odeslané před 08:43 zůstanou se starým layoutem (Telegram inline keyboard se retroaktivně nemění — neřešíme).
- Lekce zapsány do `brogiasist-lessons-learned-v1.md` jako **#40** (Python long-running + `docker cp`) a **#41** (md5 není dostatečný diag signál).
- CLAUDE.md sekce 12 doplněna o jednořádkový gotcha pointer.

**Zatímco DEV scheduler je dolů:** nespouštět ho dokud PROD běží (znovu 409). Pokud je třeba DEV testing → buď stopnout PROD, nebo dočasný separátní bot token.

---

## ⚠️ UPDATE 2026-04-27 — Co se stalo v této session

**HOTOVO** (commits na branch `2`):
- `6b43643` **H1 / BUG-009** — JXA `/contacts/all` rozšířen o emails+phones,
  starý dataset (1180) smazán, re-ingest. **1181 kontaktů, 512 s email∩groups**.
- `394ec5e` **H3** — Decision flagy persist do `email_messages`
  (sql/015_decision_flags.sql), wire `no_auto_action` v classify, visual
  indikátory v notify (⭐ VIP, 👤 personal, 👥 GROUPS).
- `af5df96` **BUG-011** — case-insensitive email match v decision_engine
  (jsonb @> → jsonb_array_elements + LOWER()).
- `e37f576` **H2** — Bridge `add_task` vrací `task_id`, callback persistuje
  `of_task_id`, 3 nové handlery (`of_open`/`of_append`/`of_new`),
  notify_emails detekuje thread + speciální zpráva s 4 buttony.

**Plus** backfill 70 historických emailů → 4 dostaly is_personal flag
(Drexler RODINA 🛠, Zámečnictví KAMARADI 🥂).

**Stav PROD:**
- Apple Bridge healthy, posix_spawn fix drží (BUG-008)
- Scheduler rebuild 2× (po H3 + po H2), běží
- DB: 71 emailů (4 s is_personal), 1181 contacts, 9 decision_rules

---

## Stav repa

- **Branch:** `2` (implementace v2 — Email Semantics v1)
- **Last commit:** `e37f576` — `feat(H2): threading TG flow`
- **Tag výchozího bodu:** `v1.1` (commit `ee483ba` na main, stable PROD)
- **Push:** vše na [github.com/dxpavel/BrogiASIST/tree/2](https://github.com/dxpavel/BrogiASIST/tree/2)

## Co začíst PŘED implementací (PŘÍKAZ)

V pořadí:

1. `docs/CONTEXT-NEW-CHAT.md` — aktuální stav (po dnešní update)
2. `docs/brogiasist-semantics-v1.md` — kanonická spec, mr Pavel ji schválil
3. `docs/brogiasist-lessons-learned-v1.md` — sekce 35–37 (BUG-008 lessons)
4. `docs/BUGS.md` — BUG-008 (FIXED) + BUG-009 (group dataset disjoint, OPEN) + BUG-010 (X-Brogi-Auto Mail.app limit, OPEN)
5. **TENHLE dokument** — co je hotovo, co zbývá

---

## Komunikační pravidla (NIKDY neporušit)

Pavel má Asperger + ADHD:

- **Strukturovaně, bez omáček a keců**
- **Jedna otázka najednou** — nikdy víc
- **Nejdřív se zeptej, pak implementuj** — nikdy nerozhoduj sám
- **Označovat:** 🍏 ok/hotovo · 🍎 problém · 🐒 riziko · ⚠️ varování
- **Před UI/architekturou:** navrhni → počkej na souhlas → pak dělej
- **Před prací:** vždy přečti zdrojový kód, nikdy nepředpokládej co tam je
- **Žádné autonomní změny** — reakce na screenshot/komentář ≠ pokyn implementovat

---

## Co bylo udělané v této session (2026-04-26, 17:00–22:30)

### 1. PROD healthcheck → 4 problémy (ráno)
- Llama classify selhával: `OLLAMA_URL` v kódu vs `OLLAMA_BASE_URL` v `.env` → **fix** commit `ebd0c81` (rename + APPLE_BRIDGE_URL přidán)
- Apple Bridge nedostupný: `APPLE_BRIDGE_URL` chyběl v `.env` → fix v stejném commitu

### 2. Email Semantics v1 — **finální spec**
- `docs/brogiasist-semantics-v1.md` (660 řádků, 20 sekcí) — TYP/STATUS/ACTION semantika, Mermaid diagram, 19 skupin kontaktů, decision rules, threading, failure handling, grafická specifikace (kostičky/fill/kazeťák), TG tlačítka per TYP
- Pavel jí schválil: **9 TYPů (ÚKOL, DOKLAD, NABÍDKA, NOTIFIKACE, POZVÁNKA, INFO, ERROR, LIST, ENCRYPTED)**, **5 STATUS** (NOVÝ/PŘEČTENÝ/ČEKAJÍCÍ/ZPRACOVANÝ/SMAZANÝ), **9 ACTION + 2undo** (prefix `2` = „to") — *2026-04-27: rozšířeno z 8 na 9 přidáním `2del` (univerzální „rychle smazat" bez učení sender=spam)*
- Skupiny kontaktů (z Apple Contacts, 19 skupin) jako orthogonal signál pro klasifikaci

### 3. BUG-008 — Apple Bridge fork() crash (HIGH)
- **Symptom:** Bridge na Apple Studio náhodně padal s SIGSEGV v `Network.framework atfork hook` — multi-threaded fork() bug
- **Workaround #1** (`OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES` env var) na macOS 26.4.1 NEFUNGOVAL
- **Proper fix** (commit `6684cfc`): `os.posix_spawn()` místo `subprocess.run()` v `run_applescript`/`run_jxa` wrapperech v `services/apple-bridge/main.py`
- Verifikováno: 50 requestů × 21 minut zátěže lokálně → 0 nových crash reportů

### 4. Blocker A — RFC 5322 headers v ingestu (commit `864ccaf`)
- `services/ingest/ingest_email.py` ukládá do `raw_payload.headers` **13 hlaviček**: Message-ID, In-Reply-To, References, List-Id, List-Unsubscribe, List-Post, Auto-Submitted, Content-Type, Cc, Bcc, Reply-To, Return-Path, X-Mailer
- Bez nich nefungovaly decision_rules header check (TYP=LIST/ENCRYPTED/ERROR detekce) ani threading

### 5. Blocker B — Apple Contacts groups (commits `8622cb5`, `0f1ba46`, `b267768`, `736ec86`, `bc76f38`, `a02ef57`)
- Apple Bridge `/contacts/all` přepsán na **JXA volání Contacts.app** (místo přímého sqlite, který launchd-spawned proces nemůže díky TCC FDA limitations — viz lessons sekce 36)
- Endpoint vrací **groups: [...]** per kontakt
- DB schema: `sql/012_apple_contacts_groups.sql` — `apple_contacts.groups jsonb` + GIN index
- `services/ingest/ingest_apple_apps.py:ingest_contacts()` ukládá groups + **hash check** (sha256 → skip ingest pokud žádné změny — config tabulka)
- Interval **6h → 12h** (Pavel: 2× denně stačí)
- Verifikace: 1180 kontaktů, 1138 ve skupinách, 18 unikátních skupin (přesně dle Pavlových)

### 6. Blocker C — decision_rules engine (commit `8ef45a7`)
- `sql/013_decision_rules.sql` — schema + 9 default pravidel:
  - priority 5: `self_sent` (X-Brogi-Auto → skip)
  - priority 10: `header_list` (List-Id → TYP=LIST + 2hotovo)
  - priority 20: `header_encrypted` (multipart/encrypted → TYP=ENCRYPTED)
  - priority 30: `header_oof` (Auto-Submitted: auto-replied → TYP=INFO)
  - priority 40: `header_bounce` (Auto-Submitted: auto-generated → TYP=ERROR)
  - priority 50: `group_vip` (skupina VIP → flag force_tg_notify, no_auto_action)
  - priority 60: `chroma_match` (cosine < 0.15 → apply_remembered)
  - priority 70: `sender_personal` (KAMARADI/MEDVEDI/RODINA/MOTO/TRAVEL/FOCENI → flag is_personal)
  - priority 80: `ai_fallback` (default → run Llama)
- `services/ingest/decision_engine.py` (~280 řádek) — `evaluate_email(email)` → decision dict
- Integrováno do `services/ingest/classify_emails.py:classify_new_emails` — engine se volá PŘED Llamou
- Verifikace na 25 reálných emailech: `header_list` matchnul 1× (Peak Design newsletter), `chroma_match` 4× (DXPSOLUTIONS DSM duplikáty), `ai_fallback` 20×
- 🍎 **Group rules nematchují** — viz BUG-009 (data ve 2 disjoint datasets)

### 7. Blocker D1 — schema rozšíření + threading (commit `34a55c3`)
- `sql/014_email_semantics_v1.sql`:
  - `email_messages` přidat sloupce: `message_id`, `in_reply_to`, `thread_id`, `of_task_id`, `of_linked_at`, `is_personal`
  - 3 partial indexy
  - Nová tabulka `pending_actions` (queue pro degraded mode)
- `ingest_email.py` extrahuje RFC headers do top-level + uloží `message_id`/`in_reply_to`/`thread_id` do nových sloupců
- Threading: nový email → JOIN přes `message_id` → zděd `thread_id` od parent (nebo self.id pokud root)

### 8. Blocker D2 — Llama prompt + per-TYP TG tlačítka (commit `7d11f75`)
- `classify_emails.py` — Llama prompt nové TYPy (6 hodnot: ÚKOL/DOKLAD/NABÍDKA/NOTIFIKACE/POZVÁNKA/INFO; ERROR/LIST/ENCRYPTED detekuje engine PŘED Llamou)
- Body 400 → 500 znaků per spec M5
- `notify_emails.py` — nová funkce `_buttons_for_typ(typ, email_id, has_unsubscribe)` per spec sekce 7
- Per-TYP tlačítka: ÚKOL=2hotovo/2of/2rem/2note/2skip/**2del**/2spam, DOKLAD=2of/2note/2hotovo/2skip/**2del**/2spam, NABÍDKA=2note/2unsub/2skip/**2del**/2spam, NOTIFIKACE=2hotovo/2skip/**2del**/2spam, POZVÁNKA=2cal/2skip/**2del**/2spam (2cal+Accept TODO v D3+), INFO=2hotovo/2skip+2unsub/**2del**/2spam, ERROR=2hotovo/2skip/**2del**/2spam, ENCRYPTED=Otevřu sám/2skip/**2del**/2spam, LIST=skip TG (auto-2hotovo)
- `2del` (přidáno 2026-04-27, var. C) je **ve všech TYPech** — univerzální „rychlé smazání" pro duplicity/šum bez označení sendera jako spam
- Callback_data zachován jako `email:<action>:<id>` (backward compat), UI text používá „2of" notaci

### 9. Blocker D3 (částečně, 4/6 endpointů, commits `5ceb3d8` + `110883e`)
- `services/apple-bridge/main.py`:
  - `GET /omnifocus/task/{task_id}` — fetch task (name, note, completed, dates)
  - `POST /omnifocus/task/{task_id}/append_note` — append k OF notes (separator + text)
  - `GET /notes/{note_id}` — fetch Apple Notes note (name, body HTML, dates)
  - `POST /notes/{note_id}/append` — HTML-safe append k Notes body
- Smoke test live: GET vratil PROVOZ task z PROD OF, POST append potvrzen `new_length: 57`
- 🐒 V OF tasku **PROVOZ** je testovací řádek `[brogi-test] BrogiASIST D3 smoke test...` — Pavel může ručně smazat

### 10. Blocker D4 — CLS fix + grafická spec (commits `a851a30` + `9da5bd2`)
- `services/dashboard/templates/base.html`:
  - **CLS fix**: Google Fonts `display=swap` → `display=optional`, logo dostal `width="40" height="40"` attributy, preconnect na fonts.gstatic.com
  - 9 CSS variables `--typ-*`, 9 `--action-*`, 5 `--status-*`
  - Třídy `.typ-box .typ-{ukol,doklad,nabidka,notifikace,pozvanka,info,error,list,encrypted}` (kostička s borderem)
  - `.action-btn .action-{of,rem,cal,note,hotovo,spam,unsub,skip,undo}` (filled button)
  - `.status-circle .status-{novy,precteny,cekajici,zpracovany,smazany}` (kazeťák kolečko ⏺▶⏸⏏⏹)
  - `.ef-chip.typ-*` rules (filter chips s TYP barvami, light rgba bg)
- `services/dashboard/templates/index.html`:
  - Filter chips: 9 nových TYP filtrů (ÚKOL/DOKLAD/NABÍDKA/NOTIFIKACE/POZVÁNKA/INFO/ERROR/LIST/ENCRYPTED) + SPAM legacy
  - Email tabulka: `<span class="typ-box ...">` místo `.badge`
  - Jinja `tc` mapping rozšířen + zachovává legacy fallback (FAKTURA→DOKLAD, NEWSLETTER→INFO, POTVRZENÍ→NOTIFIKACE, ESHOP→NABÍDKA, SPAM→ERROR)

### 11. Blocker D5 — pending queue worker (commit `ed039b1`)
- `services/ingest/pending_worker.py`:
  - `bridge_health()` — aktivní /health ping (5s timeout)
  - `enqueue(email_id, action, path, payload)` — INSERT do pending_actions
  - `drain_queue()` — SELECT pending LIMIT 20, foreach POST Bridge, throttle 2s, retry 3×, po failu TG alert
- `telegram_callback._bridge_call` refactor:
  - HTTP error (4xx/5xx) → False + TG alert
  - Connection error (timeout/refused/network) → enqueue + True („⏳ X ve frontě (Apple Studio offline)")
- `scheduler.py` — nový job `drain_queue` interval 1 min

### 12. CSS data update (dashboard `apple_contacts` count, commit `af45e3f`)
- `services/dashboard/main.py:get_db_status()` — `apple_contacts` přidán do `tables` listu

---

## Co reálně FUNGUJE (potvrzeno na PROD)

✅ Apple Bridge stable na Apple Studio (PID 13993 po posledním reload, BUG-008 fixed přes posix_spawn)
✅ 1180 kontaktů s 1138 ve skupinách v `apple_contacts`
✅ Decision engine s 9 pravidly v `decision_rules` tabulce; runs PŘED Llamou
✅ Email tabulka v dashboardu zobrazuje kostičky `.typ-box` per TYP
✅ CLS bug: pravděpodobně fixed (`display=optional`) — vyžaduje Pavlovo potvrzení po refresh
✅ Pending queue worker běží (interval 1 min); pending_actions tabulka prázdná
✅ Per-TYP TG tlačítka (callback_data backward compat)
✅ Llama prompt vrací nové TYPy
✅ RFC headers se ukládají do `email_messages.raw_payload.headers` + threading sloupce

---

## Co ZBÝVÁ (priorita HIGH → LOW)

### 🍏 HIGH — VYŘEŠENÉ 2026-04-27

| # | Co | Status |
|---|---|---|
| ~~H1~~ | ~~BUG-009 group matching~~ | **✅ FIXED commit `6b43643`** — JXA emails+phones, 512 s email∩groups |
| ~~H2~~ | ~~D5+ Threading TG flow~~ | **✅ DONE commit `e37f576`** — Bridge task_id, of_open/of_append/of_new handlery, thread JOIN detection |
| ~~H3~~ | ~~D2 action wiring decision flagů~~ | **✅ DONE commit `394ec5e`** — sql/015_decision_flags.sql, persist + visual indikátory + no_auto_action wire |
| ~~BUG-011~~ | ~~Case-insensitive email match~~ | **✅ FIXED commit `af5df96`** — JSONB array_elements + LOWER() |

### 🐒 MEDIUM

| # | Co | Náročnost | Detail |
|---|---|---|---|
| **M1** | **BUG-010: D3+ /calendar/reply + /mail/send** | ~3 h | Architectní problém: Mail.app AppleScript NEUMÍ custom headers → `X-Brogi-Auto` header (per spec sekce 13) nelze. Workarounds: (a) subject marker `[BrogiASIST-auto]` + IMAP filter na Sent folder, (b) Reply-To trick `auto+brogi@dxpsolutions.cz`. Pavel musí rozhodnout. Jakmile máme rozhodnutí, implementace 1-2 h. |
| **M2** | **2undo akce (TTL 1h)** | ~1 h | Spec sekce 3 — vrátit poslední akci na 1 krok zpět. Vyžaduje: (a) sloupec `last_action_at` + `last_action` v `email_messages` (možná jen logged v Chroma), (b) handler `undo` v `telegram_callback.py` co inverzuje akci (`2spam` → vrátit z trash, `2of` → smazat OF task přes Bridge, atd.), (c) TG tlačítko `2undo` s TTL check 1h. |
| **M3** | **STATUS kolečko v email tabulce** | ~30 min | CSS classes ready (`.status-circle .status-{novy,precteny,cekajici,zpracovany,smazany}`). Stačí v `index.html` Jinja: mapping interní `status` ('new'→'novy', 'classified'→'novy', 'reviewed'→'zpracovany') + render `<span class="status-circle status-{...}">⏺</span>` před `from_address`. |
| **M4** | **WebUI editor decision_rules** (M6 z spec) | ~3–4 h | Pavlův požadavek: konfigurovat pravidla z dashboardu. Stránka `/admin/rules` (nebo na /pravidla extension). CRUD pro decision_rules + drag&drop priority. |

### 🍏 LOW (vychytávky / dluh)

| # | Co | Náročnost |
|---|---|---|
| L1 | classification refactor na novou STATUS semantiku — Pavel rozhodl „nemigrujeme", ale **nové** emaily by měly do nových sloupců (status NOVÝ/PŘEČTENÝ atd.). Aktuálně `_save_classification` ukládá `status='reviewed'` (legacy). | ~2 h |
| L2 | Apple Bridge `/contacts/all_sqlite` legacy fallback — ponechán pro případ že FDA bude později fungovat. Můžeme smazat pokud Pavel rozhodne. | 5 min |
| L3 | Multi-action (1 email → víc akcí) — odloženo do v2 features per Pavlovo rozhodnutí | — |
| L4 | BUG-008 24h verifikace na Apple Studio — `ssh dxpavel@10.55.2.117 "ls ~/Library/Logs/DiagnosticReports/Python-*.ips"` — pokud baseline 8 nepřibude, fix drží | pasivní |
| L5 | Merge branch `2` → main + tag `v2.0` po dokončení H1+H2+H3 | 5 min |

---

## Klíčové soubory k editaci pro pokračování

```
services/ingest/decision_engine.py              # H3 (action wiring), H1 (group matching SQL)
services/ingest/notify_emails.py                # H2 (threading TG flow), H3 (action wiring), M3 (STATUS column)
services/ingest/telegram_callback.py            # H2 (of_open/of_append handlers), M2 (2undo)
services/ingest/classify_emails.py              # H3 (action wiring v classify_new_emails)
services/ingest/ingest_apple_apps.py            # H1 (po fix JXA s emails — bez změn pravděpodobně)
services/apple-bridge/main.py                   # M1 (/calendar/reply, /mail/send), H1 (JXA s emails)
services/dashboard/templates/index.html         # M3 (STATUS kolečko)
services/dashboard/templates/pravidla.html      # M4 (decision_rules editor)
sql/                                            # potenciálně nová migrace pro M2 (last_action sloupce)
```

---

## Test data v PROD DB (PROD VM 103)

```sql
-- email_messages
SELECT count(*) AS total,
       count(*) FILTER (WHERE typ IS NOT NULL) AS klasifikovano,
       count(*) FILTER (WHERE thread_id IS NOT NULL) AS s_threadem,
       count(*) FILTER (WHERE message_id IS NOT NULL) AS s_msg_id
FROM email_messages;
-- (cca 25 emailů z dnešního deploye, většina nemá thread_id protože jsou klasifikovaný před D1)

-- decision_rules — 9 pravidel
SELECT priority, rule_name, condition_type, action_type, enabled FROM decision_rules ORDER BY priority;

-- pending_actions — prázdné
SELECT count(*) FROM pending_actions;

-- apple_contacts — 2360 (1180 starých + 1180 nových)
SELECT count(*) AS total,
       count(*) FILTER (WHERE jsonb_array_length(emails) > 0) AS s_emaily,
       count(*) FILTER (WHERE jsonb_array_length(groups) > 0) AS se_skupinami
FROM apple_contacts;

-- top skupiny
SELECT g, count(*) FROM (
  SELECT jsonb_array_elements_text(groups) AS g
  FROM apple_contacts WHERE jsonb_array_length(groups) > 0
) s GROUP BY g ORDER BY 2 DESC LIMIT 20;
```

---

## Připomínky pro novou session

1. **Apple Studio FDA pro Python.app** — nastaveno přes Pavla v System Settings, plus `killall tccd` byla potřeba. Pokud Bridge náhle vrátí `no_fda` znovu (po macOS update), je to TCC reset → Pavel musí znovu povolit.
2. **Apple Bridge launchd plist** — spouští Python přímo (ne přes bash), `EnvironmentVariables` block byl odstraněn po posix_spawn fix. **NEPŘIDÁVAT zpět** `OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES` — na macOS 26.4 nefunguje.
3. **PROD VM 103 deploy workflow:**
   ```bash
   # lokálně
   git push origin 2
   # PROD
   ssh pavel@10.55.2.231
   cd ~/brogiasist
   git pull origin 2
   # SQL migrace (pokud nová)
   docker exec -i brogiasist-postgres psql -U brogi -d assistance < sql/NNN_*.sql
   # rebuild service
   docker compose build scheduler && docker compose up -d scheduler
   # nebo dashboard
   docker compose build dashboard && docker compose up -d dashboard
   ```
4. **Apple Studio deploy workflow:**
   ```bash
   # backup
   ssh dxpavel@10.55.2.117 "cp /Users/dxpavel/brogiasist-bridge/main.py main.py.backup-$(date +%Y%m%d)"
   # scp
   scp services/apple-bridge/main.py dxpavel@10.55.2.117:/Users/dxpavel/brogiasist-bridge/main.py
   # reload launchd
   ssh dxpavel@10.55.2.117 "launchctl unload ~/Library/LaunchAgents/cz.brogiasist.apple-bridge.plist && sleep 2 && launchctl load ~/Library/LaunchAgents/cz.brogiasist.apple-bridge.plist"
   # verify
   ssh dxpavel@10.55.2.117 "curl -sm 5 http://localhost:9100/health"
   ```
5. **Decision rules edit (zatím SQL only):**
   ```bash
   docker exec -it brogiasist-postgres psql -U brogi -d assistance
   UPDATE decision_rules SET enabled = FALSE WHERE rule_name = 'group_vip';  -- vypnutí
   UPDATE decision_rules SET condition_value = '{"groups":["VIP ⏰","KAMARADI  🥂"]}' WHERE rule_name = 'group_vip';  -- edit
   ```
6. **OmniFocus testovací cleanup** — Pavel může smazat řádek `[brogi-test] BrogiASIST D3 smoke test...` z notes tasku „PROVOZ" v OF.

---

## První krok příští session

H1/H2/H3 jsou hotové. Doporučení dle náročnosti × přínos:

**Možnost A — M3 (STATUS kolečko, 30 min, vychytá UX):**
- `services/dashboard/templates/index.html` — Jinja mapping interní `status` ('new'/'classified'/'reviewed') → 'novy'/'novy'/'zpracovany' a render `<span class="status-circle status-{...}">⏺</span>` před `from_address` v email tabulce. CSS classes `.status-circle .status-{novy,precteny,cekajici,zpracovany,smazany}` jsou ready z D4.

**Možnost B — M1 (mail/send + calendar/reply, 3 h):**
- Vyžaduje rozhodnutí o headers — viz BUG-010 (4 workaroundy: subject marker / Reply-To / body footer / direct SMTP). **Pavel musí rozhodnout PŘED implementací.**

**Možnost C — M2 (2undo akce, 1 h):**
- SQL migrace + handler v telegram_callback. TTL 1h check.

**Možnost D — H2 end-to-end test:**
- Pavel klikne 2of na nějaký nový email → ověř že `of_task_id` se uložil v DB.
- Když přijde reply na ten thread → ověř že přijde 🧵 zpráva s 4 buttony.
- Smaž OF testovací task `[brogi-test H2] Smoke task_id` (id `c_7fTaZfrTO`).

Doporučuju **A → D → potom rozhodnutí o B nebo C** podle priority Pavla.

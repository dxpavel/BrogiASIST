---
Název: Známé bugy a refaktory k vyřešení
Soubor: docs/BUGS.md
Verze: 1.0
Vytvořeno: 2026-04-26
Popis: Seznam bugů a technických dluhů zjištěných během vývoje. Každý záznam = co, kde, proč, jak ověřit, návrh řešení.
---

# BrogiASIST — Bugs & Tech Debt

Pravidlo: nový bug = nový záznam s ID `BUG-NNN`. Vyřešený bug = označit `[FIXED YYYY-MM-DD commit]`, nesmazat (kvůli historii).

---

## BUG-001 — `_email_action` patří do sdíleného modulu, ne do `telegram_callback.py`

**Severita:** medium (čistý code, žádný funkční dopad)
**Zjištěno:** 2026-04-26 (větev 1, base64 přílohy session)
**Status:** **FIXED 2026-05-04 commit `3507591`** — vytvořen `services/ingest/email_actions.py` (834 ř.) se sdíleným kódem. `telegram_callback.py` zredukován z 909 → 110 ř. (-88 %), zůstal jen TG-specific (offset persist + polling loop + dispatch). `api.py` import změněn na `from email_actions import email_action`. Veřejné API: `email_action()` + `email_undo()` (drop underscore). Deployed PROD.

### Popis
Funkce `_email_action()` a její helpery (`_bridge_call`, `_mark_spam`, `_get_email_from`, `_folder_for_email`, `_calendar_for_email`, `_parse_invitation_subject`, mapy `TYP_FOLDER`, `_CAL_FROM_MAP`, `_CZ_MONTHS`, `ACTION_LABEL`) leží v `services/ingest/telegram_callback.py`, ale **nejsou** Telegram-specifické — jsou to sdílená business logika pro email akce.

### Kdo to volá
1. **Telegram callback** (`telegram_callback.py:process_callback` → `_email_action`)
2. **WebUI dashboard** (`/api/ingest/email/{id}/action/{action}` → proxy → scheduler `api.py:api_email_action` → `_email_action`)

`api.py:10` obsahuje `from telegram_callback import _email_action` — bez tohoto importu by WebUI cesta nefungovala. Zachycuje tedy logiku správně, ale architektonicky nepatří do souboru s názvem `telegram_callback`.

### Proč to vadí
- Při čtení `telegram_callback.py` čtenář předpokládá Telegram-only kód → přehlédne že se mění i WebUI chování.
- Při změně OF/REM/NOTE/CAL akcí je nutné mít jistotu, že obě cesty (TG + WebUI) chovají stejně. Jméno souboru tu jistotu zatemňuje.
- Při budoucím přidání další UI cesty (např. iOS shortcut, hlasové ovládání) bude nutné import řešit znovu.

### Návrh řešení
1. Vytvořit `services/ingest/email_actions.py` — přesunout `_email_action` + všechny helpery (přejmenovat `_email_action` → `email_action`, dropnout underscore protože už není soukromé).
2. `telegram_callback.py` — zredukovat na `process_callback`, `run_callback_loop`, `_load_offset`, `_save_offset` + import `from email_actions import email_action`.
3. `api.py` — změnit import na `from email_actions import email_action`.
4. Aktualizovat `architecture-v1.md` a `data-dictionary-v1.md`.

### Jak ověřit po opravě
- `grep -rn "_email_action\|telegram_callback" services/ingest/` → mimo `process_callback` a daemon loop nesmí být reference.
- Test: klik v TG i WebUI vyvolá identický bridge call + DB UPDATE + IMAP move.

---

## BUG-002 — Přílohy se NEUKLÁDAJÍ pro duplicitní emaily (ON CONFLICT větev)

**Severita:** HIGH (datový dluh — chybí nám fyzické soubory pro 15 emailů s `has_attachments=TRUE`)
**Zjištěno:** 2026-04-26 (větev 1, base64 přílohy session)
**Status:** **FIXED 2026-04-26 (release 1.1)** — `ingest_email.upsert_messages` ukládá přílohy i pro `is_new=False` (po check `attachments` countu) a filtruje spam (`is_spam=FALSE`). Backfill `services/ingest/backfill_attachments.py` doplnil 3 z 8 historických (Forpsi/Synology emaily ztraceny natrvalo — viz BUG-006).

### Popis
V `services/ingest/ingest_email.py:upsert_messages()`:

```python
for msg in messages:
    cur.execute("""
        INSERT INTO email_messages (...)
        VALUES (...)
        ON CONFLICT (source_id) DO UPDATE SET
            body_text = COALESCE(EXCLUDED.body_text, email_messages.body_text),
            unsubscribe_url = COALESCE(EXCLUDED.unsubscribe_url, email_messages.unsubscribe_url)
        RETURNING id, (xmax = 0) AS is_new
    """, ...)
    row = cur.fetchone()
    email_uuid, is_new = row[0], row[1]
    if is_new:
        new_count += 1
        _save_email_attachments(str(email_uuid), msg.get("attachments", []), cur)
    else:
        skip_count += 1   # ← _save_email_attachments se NIKDY nezavolá
```

`_save_email_attachments()` běží **pouze** pro nové emaily (`is_new=True`). Pokud byl email v DB **dřív, než kód uměl přílohy ukládat** (nebo dřív než byl bind mount aktivní), pak při dalším IMAP fetch je `is_new=False` → příloha se NIKDY nestáhne.

### Důsledek (stav 2026-04-26)
DB SQL stav:
```
SELECT
  COUNT(*) FILTER (WHERE has_attachments=TRUE)                 = 15
  COUNT(*) FILTER (WHERE has_attachments=TRUE AND is_spam=FALSE) = 10
  COUNT(*) FILTER (WHERE has_attachments=TRUE AND task_status='→OF') = 4
SELECT COUNT(*) FROM attachments WHERE source_type='email'    = 0
```
Bind mount `/Users/pavel/Desktop/OmniFocus/` je prázdný. Žádný `<uuid>/` adresář neexistuje.

Pavlovy reálné OF tagy (4 emaily) → nelze vůbec přiložit přílohy do OmniFocus, ani v aktuálním (lokální cesta), ani v base64 flow — fyzický soubor v systému neexistuje.

### Návrh řešení
**A) Fix ingestu** (`ingest_email.py:upsert_messages`):
- Po `RETURNING id, is_new` přidat dotaz `SELECT COUNT(*) FROM attachments WHERE source_type='email' AND source_record_id=%s`
- Pokud `count = 0` AND `msg["attachments"]` není prázdné → zavolat `_save_email_attachments()` i pro `is_new=False`
- Filtr: pokud email má `is_spam=TRUE` → přílohy nestahovat (úspora místa, spam jsme vyřadili)

**B) Backfill skript** (`services/ingest/backfill_attachments.py`):
- Najít `email_messages` kde `has_attachments=TRUE AND is_spam=FALSE` a v `attachments` jsou 0 řádků
- Pro každý: připojit IMAP (`mailbox` určuje účet), najít zprávu přes Message-ID search v aktuálním folderu (`folder` z DB) s fallbackem na INBOX
- Re-extract přílohy přes existující `_extract_attachments()` z `ingest_email.py`
- Uložit přes `_save_email_attachments()`
- Loguje per-email úspěch/selhání

### Jak ověřit po opravě
```sql
-- Mělo by být 0 (nebo jen spam):
SELECT COUNT(*) FROM email_messages e
WHERE has_attachments=TRUE AND is_spam=FALSE
  AND NOT EXISTS (
    SELECT 1 FROM attachments a
    WHERE a.source_type='email' AND a.source_record_id = e.id
  );
```
A na disku v `/Users/pavel/Desktop/OmniFocus/<uuid>/<filename>` musí soubory existovat.

---

## BUG-003 — Data dictionary popisuje neexistující sloupce v tabulce `attachments`

**Severita:** medium (matoucí dokumentace, vede k chybám při psaní dotazů)
**Zjištěno:** 2026-04-26 (větev 1, base64 přílohy session)
**Status:** **FIXED 2026-04-26 (release 1.1)** — `data-dictionary-v1.md` opraven na realitu (`storage_path`, `mime_type`, `ingested_at`). Doplněna nota o Mac path v `storage_path` a o spam filtru v ingestu.

### Popis
`docs/brogiasist-data-dictionary-v1.md` (sekce "attachments") popisuje sloupce:
```
| id | source_type | source_record_id | filename | file_path | mac_path | content_type | size_bytes | saved_at |
```

Reálné schéma (`sql/001_init.sql:53`):
```sql
CREATE TABLE IF NOT EXISTS attachments (
    id               UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    source_type      VARCHAR(32)  NOT NULL,
    source_record_id UUID         NOT NULL,
    filename         VARCHAR(512) NOT NULL,
    storage_path     VARCHAR(1024) NOT NULL,   -- ← ne file_path/mac_path
    mime_type        VARCHAR(128),              -- ← ne content_type
    size_bytes       INTEGER,
    ingested_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()  -- ← ne saved_at
);
```

`ingest_email.py` zapisuje do `storage_path` Mac cestu (po replace `/app/attachments` → `/Users/pavel/Desktop/OmniFocus`). Tedy v jednom sloupci máme HOST cestu (Mac), ne kontejnerovou.

### Návrh řešení
- Opravit `data-dictionary-v1.md` aby odrážel realitu (`storage_path`, `mime_type`, `ingested_at`)
- V `lessons-learned-v1.md` přidat krátkou poznámku „attachments.storage_path obsahuje Mac cestu, ne kontejnerovou" — protože scheduler ji čte z DB a posílá Apple Bridge

### Jak ověřit po opravě
```bash
docker exec brogi_postgres psql -U brogi -d assistance -c "\d attachments"
# musí odpovídat tomu co je v data-dictionary
```

---

## BUG-004 — Forpsi/Synology: složka `BrogiASIST/HOTOVO` neexistuje, MOVE tiše selže

**Severita:** HIGH (ztráta emailů — netušíme kde reálně skončily)
**Zjištěno:** 2026-04-26 (větev 1, backfill diagnostika)
**Status:** **FIXED 2026-05-04 (commit TBD)** — `imap_actions.py` přidán per-host `_brogi_path(host, sub)` (Forpsi/Synology Cyrus → `INBOX.BrogiASIST.X`, Gmail/iCloud/Seznam → `BrogiASIST/X`) + `_folder_exists()` pre-flight check. `move_to_brogi_folder` ověřuje existenci cíle PŘED `_uid_move` a vrací False bez DB update pokud cíl chybí. `ensure_brogi_folders.py` zůstává jako bootstrap pro nové účty.

### Popis
Kód `imap_actions.move_to_brogi_folder` cílí MOVE na `BrogiASIST/<subfolder>` (Gmail/iCloud syntaxe). Pro Forpsi by měl být folder s prefixem `INBOX.` a separátorem `.` — tedy `INBOX.BrogiASIST.HOTOVO`.

Reálný seznam složek na `postapro@dxpavel.cz` (Forpsi):
```
INBOX
INBOX.HOTOVO            ← Pavlova vlastní hierarchie HOTOVO/...
INBOX.HOTOVO.DODAVATELE
INBOX.HOTOVO.KLIENTI
INBOX.Trash
INBOX.Deleted Messages
... (žádný BrogiASIST)
```

`BrogiASIST/HOTOVO` ani `INBOX.BrogiASIST.HOTOVO` v účtu **neexistuje**. Pavel má vlastní `INBOX.HOTOVO` se subhierarchií.

### Důsledek (potvrzeno)
2 OF tagované emaily (`73485751…`, `8787290f…` — FORPSI proforma faktury) byly v DB označeny `folder=BrogiASIST/HOTOVO`, ale na IMAPu **nejsou nikde**:
- Backfill prohledal všech 27 dostupných složek + Trash + Deleted Messages přes Message-ID search → 0 nálezů
- Pravděpodobně `_uid_move` zavolal MOVE/COPY+DELETE+EXPUNGE na neexistující cíl → email zmizel

### Návrh řešení
1. **Akutní (před PROD):** přidat per-host folder-naming mapping do `imap_actions.move_to_brogi_folder`. Pro Forpsi: `dest = "INBOX.BrogiASIST." + subfolder` + `_ensure_folder()` před MOVE.
2. **Lepší:** respektovat Pavlovu existující hierarchii — pokud `INBOX.HOTOVO` existuje, používat ji (ne BrogiASIST). Konfigurovatelný mapping per-mailbox do `config` tabulky.
3. **Pre-flight check:** před každým MOVE volat `m.list()` a ověřit existenci cíle. Pokud cíl neexistuje a `_ensure_folder` selže, **akce musí selhat** (return False) — ne tiše udělat COPY+DELETE+EXPUNGE bez existujícího cíle.

### Jak ověřit po opravě
```python
# Pro každý IMAP účet:
m.list()  # vypsat
# Pro každý subfolder z TYP_FOLDER + HOTOVO/CEKA: ověřit že po _ensure_folder existuje
```

---

## BUG-005 — `email_messages.folder` se aktualizuje I PŘI selhaném IMAP MOVE

**Severita:** HIGH (DB lže — `folder` říká kde email JE, ale on tam není)
**Zjištěno:** 2026-04-26 (větev 1, backfill diagnostika; přímý důsledek BUG-004)
**Status:** **FIXED 2026-05-04 (commit TBD)** — `_uid_move` nyní raise `RuntimeError` pokud MOVE i COPY selžou (žádný silent fallthrough). Try/except v `move_to_brogi_folder` / `move_to_trash` chytí výjimku → `_update_db_folder` se NEZAVOLÁ → DB zůstává konzistentní. Plus pre-flight check existence cíle v `move_to_brogi_folder` (BUG-004 fix).

### Popis
V `imap_actions.move_to_brogi_folder` (a podobně `move_to_trash`):
```python
try:
    m = connect(acc)
    _ensure_folder(m, dest)
    m.select(folder or "INBOX")
    _uid_move(m, str(imap_uid), dest)   # ← může selhat tiše (COPY+DELETE+EXPUNGE bez OK)
    m.logout()
    _update_db_folder(email_id, dest, mark_read=True)   # ← DB se updatuje vždy
    log.info(...)
    return True
```

`_uid_move` má fallback `COPY+DELETE+EXPUNGE` pokud MOVE vrátí non-OK. Ale když i COPY selže (např. cílová složka neexistuje a `_ensure_folder` ji nevytvořil), funkce nevyhazuje exception. `_update_db_folder` proběhne → DB tvrdí že email je v `BrogiASIST/HOTOVO`, ve skutečnosti zmizel.

### Důsledek
- Backfill nemůže email najít (DB folder ukazuje místo kde nikdy nebyl)
- Auditní log akcí (ChromaDB) říká "OF přidáno, email v HOTOVO" — ale email je smazaný
- Pavel netuší že přišel o data

### Návrh řešení
1. `_uid_move` musí **vyhazovat exception** pokud MOVE i COPY selhaly. Žádný silent fallthrough.
2. `_update_db_folder` volat **JEN** po úspěšném IMAP commit (po explicit OK z MOVE/COPY).
3. Pre-flight: před `_uid_move` ověřit že cíl existuje (`m.list(pattern=dest)`). Pokud ne a `_ensure_folder` ho nevytvoří → return False, žádná DB změna.

### Jak ověřit po opravě
- Test scénář: vyžádat MOVE na neexistující složku co `m.create()` odmítne → akce musí vrátit `False`, DB pole `folder` zůstává původní, email v IMAP zůstává v původní složce.

---

## BUG-006 — Datový dluh: 12 emailů s `folder='BrogiASIST/*'` v DB pravděpodobně neexistuje na IMAPu

**Severita:** medium (audit/historie — kód běží dál, ale DB lže o stavu)
**Zjištěno:** 2026-04-26 (větev 1, audit po BUG-004 mitigaci)
**Status:** OPEN — odloženo na samostatnou session (čištění dat)

### Popis
Po vytvoření BrogiASIST hierarchie (BUG-004 mitigace) jsme se podívali zpětně do DB:

| Mailbox | Server | Emailů s folder=BrogiASIST/* | Mohlo to fungovat? |
|---|---|---|---|
| dxpavel@gmail.com | Gmail | 9 | ✅ ano (HOTOVO/NEWSLETTER/FAKTURA tam před tím existovaly) |
| dxpavel@icloud.com | iCloud | 8 | ✅ ano (HOTOVO/CEKA/NEWSLETTER existovaly) |
| pavel@dxpsolutions.cz | Synology | 7 | ❌ NE — Synology vůbec žádné `BrogiASIST/*` neměla |
| postapro@dxpavel.cz | Forpsi | 3 | ❌ NE — Forpsi taky neměla |
| support@dxpsolutions.cz | Synology | 2 | ❌ NE |

**Suspektně ztracených na IMAPu: 12 emailů** (Synology 9 + Forpsi 3). DB tvrdí `folder=BrogiASIST/HOTOVO`, ale v okamžiku akce ta složka neexistovala → kombinace BUG-004 + BUG-005 → email zmizel přes COPY+DELETE+EXPUNGE bez existujícího cíle.

### Co přesně víme
- DB má `subject`, `from_address`, `body_text`, `to_addresses`, `sent_at` → audit informací zachován
- ChromaDB `email_actions` collection má embeddings + akce → learning není ohrožen, `find_repeat_action` funguje dál
- Co chybí: **fyzická zpráva na IMAPu** (raw MIME, přílohy)
- Pro emaily s `has_attachments=TRUE` v této skupině → nemůžeme získat přílohy (potvrzeno backfillem 2026-04-26 — Forpsi 2× postapro proforma + Synology 1× Louda Auto)

### Návrh řešení
1. **Per-email diagnostika** — pro 12 suspektních: Message-ID search po `INBOX`, `INBOX.Trash`, `INBOX.Deleted Messages`, `INBOX.HOTOVO` na příslušném účtu. Synology má omezení (lesson #1: SEARCH HEADER vrací prázdné) → fallback ruční fetch+porovnání.
2. **Per-email rozhodnutí:**
   - Najde se → `move_to_brogi_folder()` znovu (teď už složky existují)
   - Nenajde se → flagovat `email_messages.imap_lost = TRUE` (nový sloupec migrace 012) + zachovat v DB pro audit
3. **ChromaDB audit** — projít akce pro tyto emaily a ověřit že learning vzory dávají smysl (např. že 12 ztracených není 50 % všech OF akcí — pak by Chroma byla nepoužitelně zkreslená).

### Jak ověřit po opravě
```sql
SELECT COUNT(*) FROM email_messages
WHERE folder LIKE 'BrogiASIST/%'
  AND mailbox IN ('pavel@dxpsolutions.cz', 'postapro@dxpavel.cz',
                  'support@dxpsolutions.cz', 'brogi@dxpsolutions.cz', 'servicedesk@dxpsolutions.cz');
-- Po opravě: každý buď v IMAPu existuje a folder je správný, nebo má imap_lost=TRUE.
```

### Souvislost s primárním úkolem (base64 přílohy)
**Žádná.** Base64 flow řeší novou OF akci a folder hierarchie už existuje. BUG-006 je čistě úklid historie.

---

## BUG-007 — Duplicita lokací příloh na DEV (bind mount + Apple Bridge písaní)

**Severita:** low (tech debt, neblokuje funkci)
**Zjištěno:** 2026-04-26 (větev 1, v 1.1 finalizace)
**Status:** ACKNOWLEDGED — řešení odloženo na PROD migraci (DEV se pak zastaví)

### Popis
Na DEV scheduler píše přílohy přes bind mount `/Users/pavel/Desktop/OmniFocus:/app/attachments` → soubory končí na `~/Desktop/OmniFocus/<email_id>/`. Apple Bridge (po OF akci) je dekóduje z base64 a píše znovu na `~/Desktop/BrogiAssist/<email_id>/`. **Stejný soubor 2× na disku.**

Pavel toleruje („lépe 2 než nic" pro DEV testování).

### Důsledek pro PROD (řešeno tam)
Na PROD scheduler běží na BrogiServer (Linux) — bind mount na `~/Desktop/OmniFocus` neexistuje. Přílohy se uloží jen interně na BrogiServer disk (např. `/var/lib/brogiasist/attachments/`) a Apple Bridge na Apple Studio uloží do `~/Desktop/BrogiAssist/`. Pavel uvidí **jen `~/Desktop/BrogiAssist/`** — to je „pravdivá" lokace.

### Návrh řešení (při PROD migraci)
1. V `docker-compose.yml` na PROD **odstranit** bind mount `./Desktop/OmniFocus:/app/attachments`
2. V `services/ingest/ingest_email.py` přepnout `_MAC_ATTACHMENTS_DIR` → fallback na `_ATTACHMENTS_DIR` (`/app/attachments`) — tedy DB `attachments.storage_path` na PROD bude obsahovat **kontejnerovou cestu**, ne Mac cestu
3. V `services/ingest/telegram_callback.py:_read_attachments_b64` upravit replace logiku — pokud `_HOST_PREFIX` není v cestě, číst přímo (zpětně kompatibilní)
4. Po PROD migraci **DEV stack zastavit nebo zrušit** — bind mount tam přestane být relevantní
5. Pak DEV-Mac `~/Desktop/OmniFocus/` lze ručně smazat (nepoužívá se)

### Jak ověřit po opravě (PROD)
```bash
ssh dxpavel@10.55.2.117  # Apple Studio
ls ~/Desktop/BrogiAssist/   # ← jediná lokace souborů
ssh forpsi-root             # BrogiServer
docker exec brogiasist_scheduler ls /app/attachments/   # ← kontejner storage, Pavel nepřístup
# `~/Desktop/OmniFocus/` na BrogiServeru NEEXISTUJE — bind mount nezavedený
```

---

## BUG-008 — Apple Bridge náhodně padá v multi-threaded `fork()` (macOS bug)

**Severita:** HIGH (každý crash = ztráta in-flight requestu na Apple Studio)
**Zjištěno:** 2026-04-26 (PROD provoz)
**Status:** FIXED 2026-04-26 — proper fix (`os.posix_spawn`), commit `6684cfc` na branch `2`

⚠️ **Workaround #1 (`OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES`) na macOS 26.4.1 NEFUNGOVAL.** Apple ho v některém release ignoruje. Fix nasazen v 19:33, nový crash o 15 minut později (19:48). Eskalace na proper fix #3.

### Popis
Apple Bridge na PajaAppleStudio (10.55.2.117, Python 3.11.15 + uvicorn) náhodně padá s `EXC_BAD_ACCESS (SIGSEGV)` — v jeden den dva crashe (18:17, 19:28). Crash report ukazuje:

```
*** multi-threaded process forked ***
crashed on child side of fork pre-exec

Thread 0 Crashed:
0  libsystem_trace.dylib  _os_log_preferences_refresh + 56
1  libsystem_trace.dylib  os_log_type_enabled + 772
2  libnetworkextension.dylib  NEFlowDirectorDestroy + 64
3  Network  nw_path_release_globals + 164
4  Network  nw_settings_child_has_forked() + 296
5  libsystem_pthread.dylib  _pthread_atfork_child_handlers + 76
6  libsystem_c.dylib  fork + 112
7  _posixsubprocess  do_fork_exec + 68
8  _posixsubprocess  subprocess_fork_exec + 928
```

### Důsledek
- Padá **child** proces po fork() → parent (uvicorn) přežije, launchd KeepAlive ho nerestartuje
- Konkrétní HTTP request (např. `/omnifocus/tasks` přes osascript) selže s timeout/connection error na straně scheduleru
- Apple Studio nemá log file (`~/Library/Logs/cz.brogiasist.apple-bridge.log` neexistuje)
- Random behaviour: `/contacts/all` vrací 500, ostatní endpointy občas selžou

### Příčina
Apple od macOS Catalina nedoporučuje `fork()` v multi-threaded apps. uvicorn má vlákna, `subprocess.Popen` v handlerech volá `fork()`+`exec()`, v child procesu se Apple's `Network.framework` `nw_settings_child_has_forked()` atfork hook pokusí refreshnout `_os_log_preferences` a segfaultuje, protože v child memory není inicializovaný log subsystem.

### Aplikovaná řešení

#### Workaround #1 (NEFUNGOVAL na macOS 26.4.1) — env var `OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES`
Nasazeno 19:33, nový crash 19:48 (o 15 min později). Apple v macOS 26.x env var ignoruje. **Odstraněno z plistů během cleanup commitu.**

#### Proper fix (FUNGUJE) — `os.posix_spawn()` místo `subprocess.run()`
Refactor 2 wrapper funkcí v `services/apple-bridge/main.py`:

```python
def _spawn_osascript(args: list[str], timeout: int) -> tuple[int, str, str]:
    # os.posix_spawn() s file_actions (POSIX_SPAWN_DUP2 + POSIX_SPAWN_CLOSE pro pipes)
    # → atomický syscall, neforkuje, atfork hooks Apple's Network.framework se nevolají
```

`run_applescript` a `run_jxa` volají tento helper, API zůstává — 12 callsites se nemění.

**Verifikace:**
- Lokální stress test (MacBook, M1 Ultra: nope → MacBook Pro): 50 requestů `/omnifocus/tasks`, 5 paralelních osascript subprocesů, 21 minut zátěže → **0 nových crash reportů**
- Deploy na Apple Studio: commit `6684cfc` (branch `2`), `scp main.py` + `launchctl unload/load`
- `/health` OK po reload

### Co dál sledovat
24h po deployi: `ssh dxpavel@10.55.2.117 "ls ~/Library/Logs/DiagnosticReports/Python-*.ips"` — pokud baseline 8 nepřibude, fix drží.

### Jak ověřit po opravě
```bash
# Na Apple Studio
ls -la ~/Library/Logs/DiagnosticReports/Python-*.ips
# → po fixu by neměly přibývat nové crash reporty Pythonu

# Verifikace plist obsahuje fix
/usr/libexec/PlistBuddy -c 'Print :EnvironmentVariables:OBJC_DISABLE_INITIALIZE_FORK_SAFETY' \
  ~/Library/LaunchAgents/cz.brogiasist.apple-bridge.plist
# → YES

# Bridge musí běžet
curl -sm 5 http://localhost:9100/health
# → {"ok":true,"ts":"..."}
```

---

## BUG-009 — Group matching v decision_rules nefunguje (disjoint datasets v apple_contacts)

**Severita:** HIGH (blokuje VIP/personal pravidla v decision_rules engine)
**Zjištěno:** 2026-04-26 (blocker C verifikace)
**Status:** **FIXED 2026-04-27 commit `6b43643`** — JXA `/contacts/all` rozšířen o per-kontakt `emails`/`phones`, starý dataset (1180 řádků) smazán, re-ingest. Po fixu: 1181 kontaktů, **512** s `email ∩ groups` (před: 0). Decision engine query teď matchne. Verify: 4 backfilled emaily správně dostaly `is_personal=true` (Drexler RODINA 🛠, Zámečnictví KAMARADI 🥂, ...).

### Popis
Tabulka `apple_contacts` obsahuje **2360 řádků** ve dvou disjoint datasets:

| Dataset | Počet | emails | groups | source_id format |
|---|---|---|---|---|
| Starý (DEV/MacBook ingest, před PROD migrací) | 1180 | ✅ má | ❌ nemá | `XXX:ABPerson` (MacBook ZUNIQUEID) |
| Nový (PROD/Apple Studio JXA, 2026-04-26 19:06) | 1180 | ❌ prázdné `[]` | ✅ má (1138 ve skupinách) | `XXX:ABPerson` (Apple Studio ZUNIQUEID — JINÉ UUIDs!) |

`person.id()` z JXA Contacts.app vrací stejný formát jako sqlite ZUNIQUEID,
ale **lokální UUIDs jsou per-Mac unikátní** (i přes iCloud sync). ON CONFLICT
matching přes `source_id` selhal → vznikly duplicity.

### Důsledek
Decision rules engine v `services/ingest/decision_engine.py:_eval_group()`
dělá SQL JOIN:

```sql
SELECT groups FROM apple_contacts
WHERE EXISTS (SELECT 1 FROM jsonb_array_elements(emails) AS e
              WHERE LOWER(e->>'value') = LOWER(<sender>))
  AND jsonb_array_length(groups) > 0
```

**Žádný řádek v DB nemá současně neprázdné `emails` AND `groups`** → query
nikdy nematchne → pravidla `group_vip` (priority 50) a `sender_personal`
(priority 70) **nikdy netriggerují**, i když je sender v Pavlovo adresáři.

### Návrh řešení
1. Rozšířit JXA `/contacts/all` v `services/apple-bridge/main.py` o per-kontakt
   `p.emails().map(...)` a `p.phones().map(...)` — bude pomalejší (1180 × 3
   bridge calls = ~3 min, timeout zvýšit na 600s).
2. SQL: `DELETE FROM apple_contacts WHERE ingested_at < '2026-04-26 19:06:00'`
   — odstraní starý dataset (zůstane 1180 nových se kompletními daty).
3. Trigger ingest manuálně: `docker exec -w /app brogiasist-scheduler python3 -c
   'from ingest_apple_apps import ingest_contacts; ingest_contacts()'`
4. Verify: `SELECT count(*) FROM apple_contacts WHERE jsonb_array_length(emails) > 0
   AND jsonb_array_length(groups) > 0;` (musí > 0)

Náročnost: ~2 h vč. testování.

### Jak ověřit po opravě
```bash
# spustit standalone test decision engine na 25 reálných emailech
docker cp services/ingest/test_decision.py brogiasist-scheduler:/app/
docker exec -w /app brogiasist-scheduler python3 test_decision.py
# výstup musí ukázat aspoň 1× 'group_vip' nebo 'sender_personal' v matched_rules
```

---

## BUG-010 — Mail.app AppleScript neumí custom headers (X-Brogi-Auto)

**Severita:** MEDIUM (blokuje D3+ implementaci `/calendar/reply` + `/mail/send`)
**Zjištěno:** 2026-04-26 (blocker D3 audit)
**Status:** OPEN — vyžaduje architektní rozhodnutí Pavla

### Popis
Per `docs/brogiasist-semantics-v1.md` sekce 13: bot odesílá Accept/Decline
reply pozvánek a generic emails s headerem `X-Brogi-Auto: <action>`. IMAP
filter na Sent folder pak ignoruje takto označené emaily (aby je bot zase
neklasifikoval).

**Apple's Mail.app AppleScript dictionary** ale neumožňuje nastavit custom
headers při `make new outgoing message`. Properties co lze nastavit:
`subject`, `content`, `sender`, `to recipients`, `cc recipients`, `visible`,
`message signature`. **Žádná `headers` collection.**

### Důsledek
Implementace `/mail/send` endpointu v Apple Bridge má 3 možnosti, žádná
ideální:

| Workaround | Výhoda | Nevýhoda |
|---|---|---|
| **(a) Subject marker** `[BrogiASIST-auto:<action>]` na konec | snadná detekce v IMAP | zaplevelí subject pro příjemce |
| **(b) Reply-To header** Mail.app to umí přes `with properties {reply to:...}` *(neověřeno)* | čistý subject | vyžaduje speciální mailbox `auto+brogi@dxpsolutions.cz` (setup) |
| **(c) Body footer** `<!-- X-Brogi-Auto: <action> -->` na konec body | neviditelné v textových klientech | viditelné v plaintext, HTML klienti to vidí; ne 100% spolehlivé |
| **(d) Direct SMTP** mimo Mail.app | full control nad headers | per-account SMTP credentials, není identický s Mail.app sent folder |

### Návrh
Pavel rozhodne mezi (a)/(b)/(c)/(d). Jakmile máme rozhodnutí:
- 1–2 h implementace `/mail/send` endpointu v Apple Bridge
- 1 h implementace `/calendar/reply` (vrstva nad `/mail/send` s ICS reply payload)
- 30 min IMAP filter logic v `ingest_email.py` (skip pokud detekce auto-marker)

### Jak ověřit po opravě
1. Pavel klikne `📅 2cal+Accept` v TG na pozvánku → bot vytvoří calendar event
   + odešle Accept reply pozvateli
2. Bot reply skončí v Sent folderu — IMAP IDLE ho zachytí
3. Ingest detekuje auto-marker → skip klasifikace (neuloží do `email_messages`
   nebo uloží s `status='ignored'`)
4. Pavel v dashboardu nevidí svůj vlastní reply jako nový k klasifikaci

---

## BUG-011 — Case-insensitive email match v decision_engine group rules

**Severita:** MEDIUM (skrytá příčina nematchování pro ~30 % personal kontaktů)
**Zjištěno:** 2026-04-27 (po H3 deploy + smoke test)
**Status:** **FIXED 2026-04-27 commit `af5df96`**

### Popis
Po fixu BUG-009 jsme verifikovali decision engine: pro `roman.hruby@schmachtl.cz`
(MEDVEDI 🧸) vrátil `is_personal=true`. Ale pro `Koscusko@seznam.cz` (FOCENI 📸,
v adresáři jako "Honzik Košťál") rule **nematchla** — flag zůstal `false`.

### Příčina
DB hodnota `Koscusko@seznam.cz` má capital K (původně psaný v Apple Contacts).
`_extract_email_addr()` vrací lowercase `koscusko@seznam.cz`. JSONB `@>` operátor
je **case-sensitive**, containment match selhal:

```python
# PŘED: case-sensitive
SELECT groups FROM apple_contacts
WHERE emails @> '[{"value": "koscusko@seznam.cz"}]'::jsonb  ← FAIL (DB má "Koscusko")
```

### Fix
Nahrazeno přes `jsonb_array_elements` + oboustranné `LOWER()`:

```python
SELECT groups FROM apple_contacts
WHERE EXISTS (SELECT 1 FROM jsonb_array_elements(emails) AS e
              WHERE LOWER(e->>'value') = LOWER(%s))
  AND jsonb_array_length(groups) > 0
```

### Performance impact
Per-rule call dělá 1 SQL query na 1181 řádků JSONB scan. Bez indexu cca ~ms.
Pokud bude `decision_rules` engine spouštěn pro velký objem (>100 emailů/min),
zvážit funkční index `CREATE INDEX ON apple_contacts USING gin
((lower(emails::text)) gin_trgm_ops)`. Dnes není potřeba.

### Jak ověřit
```python
from decision_engine import evaluate_email
d = evaluate_email({'from_address': 'Koscusko@seznam.cz', 'subject': 't',
                    'raw_payload': {'headers':{}}, 'body_text': ''})
assert d['is_personal'] is True
assert 'FOCENI 📸' in d['matched_groups']
```

---

## BUG-012 — `fetch_messages` spadne na `data[0]=None` z iCloud IMAP SEARCH

**Severita:** medium (iCloud account negeneruje real-time IDLE notifikace, jen 30min scan funguje)
**Zjištěno:** 2026-05-04 (drift fix session)
**Status:** FIXED 2026-05-04 commit `<TBD>`

### Popis
[services/ingest/ingest_email.py:192](services/ingest/ingest_email.py:192) — po `m.uid('SEARCH', None, f'SINCE {since_str}')` kód volal `data[0].split()` bez ošetření. iCloud IMAP občas vrací `data=[None]` (prázdný výsledek nebo dočasný server glitch) → `AttributeError: 'NoneType' object has no attribute 'split'`.

V logu PROD: každých 30s `[ERROR] [dxpavel@icloud.com] Chyba: 'NoneType' object has no attribute 'split' — reconnect za 30s`. IDLE listener pro iCloud v cyklickém crash/reconnect.

### Důsledek
- iCloud nedostává **real-time** notifikace přes IMAP IDLE (každý nový email čeká na 30min `job_email_scan` fallback místo na okamžitý IDLE push).
- Logy zaspaměny chybou — ostatní bugy se v šumu hůř hledají.
- Stejný anti-pattern (`data[0].split()` bez guard) je v 4 backfill skriptech, ale ty mají `if typ == "OK" and data[0]` guard PŘED voláním → tam OK.

### Fix
```python
# před:
uids = data[0].split()
# po:
uids = (data[0] or b"").split() if data else []
```

Plus pojistka pro `to_raw` (může být None po `decode_header_value`):
```python
to_raw = decode_header_value(msg.get("To", "")) or ""
```

### Jak ověřit po opravě
```bash
ssh pavel@10.55.2.231 "docker logs brogiasist-scheduler --since 5m 2>&1 | grep 'NoneType.*split'"
# musí vrátit prázdný výsledek
ssh pavel@10.55.2.231 "docker logs brogiasist-scheduler --since 5m 2>&1 | grep 'IMAP login OK: dxpavel@icloud.com'"
# musí ukázat health login bez následného crashe
```

### Lessons
Sekce **44** v `brogiasist-lessons-learned-v1.md`.

---

## BUG-013 — Llama vrací raw placeholder `<0.0-1.0>` místo čísla v `confidence`

**Severita:** medium (selže klasifikace celého emailu — `continue` v outer loop, email zůstane v `status='new'`)
**Zjištěno:** 2026-05-04 (PROD log audit po BUG-012 deploy, 13:27:35 UTC)
**Status:** **FIXED 2026-05-04 commit `b8e88a9`** — try/except + range check (0.0-1.0), fallback 0.5 + warning log. Deployed PROD 2026-05-04 ~14:51 UTC. Verifikováno: postižený email 7c5bc148 reklasifikován ÚKOL.

### Popis
[services/ingest/classify_emails.py:331](services/ingest/classify_emails.py:331) — `confidence = float(result.get("confidence", 0.5))` bez sanitize.

Llama prompt template ([classify_emails.py:54](services/ingest/classify_emails.py:54)) má placeholder `"confidence": <0.0-1.0>`. Občas (≈1×/den dle observation) Llama tu hodnotu **echo-uje doslova** místo aby ji vyhodnotila — vrátí `{"confidence": "<0.0-1.0>"}`. `float("<0.0-1.0>")` → `ValueError: could not convert string to float`. Výjimka propadne do outer try/except, email se logguje jako `[ERROR] classify <id>: could not convert string to float: '<0.0-1.0>'` a klasifikace skončí.

### Důsledek
- Email zůstane neklasifikovaný (`status='new'`, `typ=NULL`)
- TG notifikace neproběhne — Pavel se o emailu nedozví dokud někdo ručně netriggerne re-classify
- Aktuálně postižen: `7c5bc148-2f4c-4872-ac54-8d48cb5b2d6f` (2026-05-04 13:27:35)

### Příčina
Sanitize logika v [classify_emails.py:332-355](services/ingest/classify_emails.py:332) řeší **`typ`** (whitelist `_VALID_TYP`) a **`task_status`** (whitelist `_VALID_TASK_STATUS`), ale **`confidence` chybí**. Stejný anti-pattern jako sanitize problému z lekce **#42**, jen pro číselný field.

### Návrh řešení
```python
# services/ingest/classify_emails.py:331
raw_confidence = result.get("confidence", 0.5)
try:
    confidence = float(raw_confidence)
    if not (0.0 <= confidence <= 1.0):
        raise ValueError(f"out of range: {confidence}")
except (TypeError, ValueError) as e:
    log.warning(f"Llama vrátila invalid confidence={raw_confidence!r}, fallback 0.5 ({email_id}): {e}")
    confidence = 0.5
```

Plus zvážit retry Llama call pokud více polí vrátí raw placeholders (signál že model je v špatném stavu / temp glitch).

### Jak ověřit po opravě
```bash
ssh pavel@10.55.2.231 "docker logs brogiasist-scheduler --since 24h 2>&1 | grep -E 'could not convert.*0\\.0-1\\.0|invalid confidence'"
# musí: 0× ValueError, případně N× warning "fallback 0.5"
```

A re-classify postiženého emailu:
```sql
UPDATE email_messages SET status='new', typ=NULL WHERE id='7c5bc148-2f4c-4872-ac54-8d48cb5b2d6f';
```
Pak `classify_new_emails` proběhne v dalším 5min cyklu.

---

## BUG-014 — `mark_read` selhává s `STORE illegal in state AUTH` po `move_to_trash`

**Severita:** medium (false ERROR v logu po každé `2del`/`2spam` akci na Gmail/Synology, email reálně už v Trash)
**Zjištěno:** 2026-05-04 (PROD log audit, 13:32:23 + 13:47:00 UTC)
**Status:** **FIXED 2026-05-04 commit `e5df8a7`** — `_mark_read_after_action` skip pro Trash/Deleted/Spam/Junk folders + `mark_read` check `m.select()` návrat. Deployed PROD 2026-05-04 ~14:51 UTC.

### Popis
Sekvence z PROD logu:
```
13:32:22 [INFO] move_to_trash OK: dxpavel@gmail.com uid=114152 → [Gmail]/Trash
13:32:23 [ERROR] mark_read dxpavel@gmail.com uid=114152: command STORE illegal in state AUTH, only allowed in states SELECTED
```

Po úspěšném `move_to_trash` se volá `_mark_read_after_action` → `mark_read(email_id)`. To načte z DB `(mailbox, uid, folder)` = `(dxpavel@gmail.com, 114152, [Gmail]/Trash)` — folder už je updatovaný (`_update_db_folder` to udělalo v rámci move). Ale **původní UID 114152 v `[Gmail]/Trash` neexistuje** — Gmail při MOVE generuje nový UID v cílové složce (UIDVALIDITY se mění mezi folders).

Pak [imap_actions.py:112-113](services/ingest/imap_actions.py:112):
```python
m.select(imap_folder)            # pravděpodobně vrátí non-OK (nebo OK ale uid neexistuje)
m.uid("STORE", str(imap_uid), "+FLAGS", "(\\Seen)")  # crashne s STORE illegal
```

Navíc — `m.select()` návratový kód kód ignoruje. Pokud SELECT selže (server vrátí `BAD`/`NO`), spojení zůstane ve stavu AUTH a STORE pak vyhodí `illegal in state AUTH`.

### Důsledek
- Každá `2del`/`2spam` akce na Gmail/Synology generuje 1× false ERROR v logu (zatemňuje skutečné errory)
- Funkčně OK — email **už je v Trash**, `_update_db_folder` v `move_to_trash` taky nastavil DB `is_read=TRUE` (parametr `mark_read=True` v line 139)
- Tedy `mark_read` po `move_to_trash` je **redundantní** — práce už je hotová

### Návrh řešení
**Varianta A (preferovaná, 1 řádek):** v `_mark_read_after_action` ([imap_actions.py:174](services/ingest/imap_actions.py:174)) skip pro emaily co jsou už v Trash/Deleted:
```python
def _mark_read_after_action(email_id):
    info = get_imap_info(email_id)
    if not info:
        return
    _, _, folder = info
    if folder and any(t in folder.lower() for t in ("trash", "deleted", "spam")):
        return  # email už není v INBOX, mark_read je no-op
    mark_read(email_id)
```

**Varianta B (defensive, robustnější):** v `mark_read` ([imap_actions.py:109-113](services/ingest/imap_actions.py:109)) check návratu SELECT:
```python
typ, _ = m.select(imap_folder)
if typ != "OK":
    log.warning(f"mark_read skip: SELECT {imap_folder} failed ({typ})")
    m.logout()
    return False
m.uid("STORE", ...)
```

**Doporučuji A + B** — A řeší root cause (zbytečné volání), B je pojistka pro budoucí případy.

### Jak ověřit po opravě
```bash
# klik na 2del v TG na test email z Gmail
ssh pavel@10.55.2.231 "docker logs brogiasist-scheduler --since 5m 2>&1 | grep -E 'STORE illegal|mark_read.*Gmail'"
# musí: 0× STORE illegal, žádný mark_read pokus po move_to_trash
```

---

## Šablona pro nový bug

```markdown
## BUG-NNN — Krátký popis (jedna věta)

**Severita:** low | medium | HIGH | CRITICAL
**Zjištěno:** YYYY-MM-DD (větev X, kontext)
**Status:** OPEN | IN PROGRESS | FIXED YYYY-MM-DD commit-hash

### Popis
Co je špatně. Konkrétní soubor:řádek pokud relevantní.

### Důsledek
Co se stane / co nefunguje / co je riziko.

### Návrh řešení
Konkrétní kroky. Žádné „možná by se mohlo".

### Jak ověřit po opravě
Příkaz / SQL / test.
```

# BrogiASIST — Lessons Learned v1

> Jazyk: česky. Určeno pro budoucí vývojáře nebo AI asistenty, kteří na projektu pracují.
> Stav: 2026-04-27 (release v2 patch). Aktualizuj při každém novém zjištění.

---

## 1. IMAP — rozdíly mezi providery

### iCloud (dxpavel@me.com)
- `fetch_cmd` musí být **`BODY[]`**, ne `RFC822`.
- `RFC822` vrací prázdné `b'59 ()'` — žádná data, žádná chybová hláška, tiché selhání.
- App-specific password povinný (viz sekce 15).
- **Trash folder**: `Deleted Messages` (s mezerou — viz sekce 16 o quoting).
- **STORE flag**: musí být `(\\Seen)` s závorkami, ne `\\Seen` holý — viz sekce 16.
- **SEARCH HEADER**: používej `m.uid('SEARCH', None, 'HEADER', 'Message-ID', mid)` (separate args), ne string form `f'HEADER Message-ID "{mid}"'` — string form způsobuje `BAD Parse Error` na iCloud.

### Forpsi (brogi@, servicedesk@, support@, pavel@, postapro@)
- Správné nastavení: **port 143 + STARTTLS**.
- Port 993 SSL na Forpsi **nefunguje** — spojení selže nebo visí.
- **Trash folder**: `INBOX.Trash` (ne `Trash`!) — separator je `.`, vše pod `INBOX.` prefixem.
- **Folder separator**: `.` (tečka), ne `/` (lomítko). Složky jsou `INBOX.subfolder`, ne `subfolder`.
- **BrogiASIST složky**: na Forpsi není BrogiASIST hierarchie — pokud ji chceš, musíš použít `INBOX.BrogiASIST.HOTOVO` apod.

### Synology (mail.dxpsolutions.cz — pavel@, support@, brogi@)
- **Trash folder**: `Trash`.
- Separator: `.` (tečka).
- **SEARCH HEADER**: vrací `OK [b'']` (prázdné) i pro platná Message-IDs — pravděpodobně nepodporuje HEADER search. Použij UID přístup nebo ruční fetch+porovnání.

### Seznam (padre@seznam.cz)
- **Nepodporuje IMAP IDLE**.
- Řešení: graceful fallback — reconnect každých 30 sekund, při každém reconnectu fetch nových zpráv.
- Nepoužívej blocking IDLE smyčku pro tento účet.

### Gmail (dxpavel@gmail.com, zamecnictvi@gmail.com)
- **Trash folder**: `[Gmail]/Trash`.
- UIDs jsou per-folder — UID v INBOX se liší od UID v `[Gmail]/All Mail`.
- Starší emaily (přesunuté Gmailem do Promotions/Social) nemusejí být dostupné přes INBOX UID.
- Pro hledání přes Message-ID zahrň do seznamu: `["INBOX", "[Gmail]/All Mail", "[Gmail]/Promotions"]`.
- Složky s lomítkem (`[Gmail]/All Mail`) potřebují při `m.select()` uvozovky: `m.select('"[Gmail]/All Mail"')`.

### imapclient UID decode
- `uid` vrácené z `fetch()` může být `bytes`, ne `int`.
- Vždy normalizuj: `int(uid.decode() if isinstance(uid, bytes) else uid)`
- Bez toho padá porovnání nebo DB insert.

---

## 2. OmniFocus JXA — výkonnostní problémy

### `taskStatus()` enum — nelze JSON serializovat
- `t.taskStatus()` vrací OmniFocus enumeration type, který Python/JSON nezná.
- Error: `"Can't convert types. (-1700)"`.
- Řešení: status počítej ručně:
  ```javascript
  const completed = t.completed();
  const due = t.dueDate();
  const now = new Date();
  // overdue = due && !completed && due < now
  ```

### Per-item property access — extrémně pomalý
- Volání `t.name()`, `t.flagged()`, `t.dueDate()` zvlášť pro každý task = Apple Event pro každý atribut.
- Naměřeno: **~29 sekund pro 462 tasků**.
- Nepoužívej v produkci.

### Bulk array fetch — správný přístup
- `doc.flattenedTasks.whose({completed:false}).name()` vrátí pole všech hodnot v jednom Apple Events volání.
- Fetch celou skupinu: `.name()`, `.flagged()`, `.dueDate()`, `.note()` — každý atribut jedním voláním přes celou kolekci.
- Výrazně rychlejší než per-item.

### Rekurzivní iterace přes projekty — zastaralý přístup
- Starý pattern `doc.flattenedProjects()` → `container.tasks()` rekurzivně je pomalý a zbytečně složitý.
- Správný přístup: **`doc.flattenedTasks.whose({completed:false})`** — vrátí přímo všechny nekompletní tasky.

### JXA timeout
- Výchozí timeout 30s nestačí pro větší databáze (1000+ tasků).
- Nastav timeout na **90 sekund** (`osascript` argument nebo subprocess timeout).

### `containingProject()` — vynech pokud nepotřebuješ
- Per-task lookup projektu přes `containingProject()` je pomalý.
- Vynech z výchozího fetch cyklu; přidej pouze pokud je explicitně potřeba.

---

## 3. JXA Calendar — kompletně visí

- Calendar JXA v jakékoliv podobě **visí** (testováno na macOS 26.x).
- Calendar.app nereaguje na JXA scripting — žádná chyba, jen timeout.
- **Řešení: použij AppleScript místo JXA.**

### AppleScript — funkční, ale pomalý pro velké kalendáře
- `osascript -e 'tell application "Calendar" to ...'` funguje.
- Problém: `whose start date >= X and start date <= Y` je pomalý pro velké kalendáře.
- Garmin Connect, Siri Suggestions a podobné mají tisíce eventů — bez filtrace timeout.

### Řešení: filtruj seznam kalendářů
- Na začátku načti seznam kalendářů a skip tyto:
  - Garmin Connect
  - Siri Suggestions
  - Birthdays
  - Scheduled Reminders
  - České svátky (nebo jiné read-only feed kalendáře)
- Zpracovávej pouze uživatelské kalendáře.

### Timeout pro AppleScript Calendar
- Nastav subprocess timeout na **120 sekund**.

---

## 4. Apple Contacts — JXA příliš pomalý

### Co nefunguje
- Per-item JXA (`p.firstName()`, `p.lastName()` atd.) pro 1177 kontaktů: **timeout >120s**.
- `p.properties()` (všechno najednou per kontakt): stále timeout pro 1177 kontaktů.
- `people.firstName()` bulk: `TypeError` — Contacts JXA **nepodporuje** array property access jako OmniFocus.

### Řešení: přímé čtení sqlite databáze
- Lokace iCloud kontaktů: `~/Library/Application Support/AddressBook/Sources/<UUID>/AddressBook-v22.abcddb`
- Hlavní DB (`~/Library/Application Support/AddressBook/AddressBook-v22.abcddb`) obsahuje pouze lokální/základní kontakty — iCloud sync'd kontakty jsou v source subdirectory.
- Rychlost: **1176 kontaktů za <0.05s**.

### Core Data timestamp
- Timestamps v AddressBook sqlite jsou **seconds since 2001-01-01** (ne Unix epoch 1970-01-01).
- Konverze: `datetime(2001, 1, 1) + timedelta(seconds=ts)`

---

## 5. Apple sqlite databáze — lokace

| Aplikace | Cesta | Tabulky / poznámky |
|---|---|---|
| iMessage | `~/Library/Messages/chat.db` | `message`, `handle`, `chat` |
| Contacts (lokální) | `~/Library/Application Support/AddressBook/AddressBook-v22.abcddb` | jen lokální kontakty |
| Contacts (iCloud) | `~/Library/Application Support/AddressBook/Sources/<UUID>/AddressBook-v22.abcddb` | sync'd kontakty — **toto použij** |
| Calendar | `~/Library/Calendars/` | Full Disk Access required — bez něj `Operation not permitted` |

> Poznámka: UUID v Contacts/Sources je unikátní per zařízení — nedá se hardcodovat. Vždy prohledej adresář Sources a najdi správnou DB (`os.listdir`).

---

## 6. ChromaDB v Docker

- ChromaDB Docker image **nemá curl ani python** → standardní healthcheck (`curl http://localhost:8000`) selže při build.
- Řešení: **odstraň `healthcheck` sekci** pro `chromadb` service v `docker-compose.yml`.
- V `depends_on` u dalších services použij `condition: service_started` (ne `service_healthy`).

```yaml
# Špatně:
chromadb:
  healthcheck:
    test: ["CMD", "curl", "-f", "http://localhost:8000/api/v1/heartbeat"]

# Správně:
chromadb:
  # bez healthcheck sekce
  
dashboard:
  depends_on:
    chromadb:
      condition: service_started  # ne service_healthy
```

---

## 7. Docker networking

### host.docker.internal
- Standardní hostname pro dosažení Mac hostu z Docker kontejneru.
- Použití pro Apple Bridge: `http://host.docker.internal:9100`

### PostgreSQL port conflict
- Port 5432 na DEV může být obsazený lokálním PostgreSQL instalovaným na Macu.
- Řešení: mapuj na jiný externí port v `docker-compose.yml`:
  ```yaml
  ports:
    - "5433:5432"
  ```
- Uvnitř Docker sítě je port stále **5432**.
- V env proměnných pro Docker services: `POSTGRES_PORT: 5432`
- Pro lokální dev skripty (mimo Docker): port **5433**

---

## 8. APScheduler timezone

- `datetime.now()` vrací **naive datetime** (bez timezone info).
- APScheduler konfigurovaný s `timezone="Europe/Prague"` očekává timezone-aware datetimes pro `next_run_time`.
- Mismatch způsobuje warning: `"Run time was missed by 2:00:00"` — job se spustí se zpožděním nebo přeskočí.
- Řešení:
  ```python
  from datetime import datetime, timezone
  scheduler.add_job(..., next_run_time=datetime.now(tz=timezone.utc))
  ```

---

## 9. Python 3.14 — FastAPI kompatibilita

- FastAPI `0.115.0` není kompatibilní s Python 3.14.
- Error: `ImportError: cannot import name 'PYDANTIC_V2'`
- Řešení — použij tyto verze (nebo vyšší):
  ```
  fastapi>=0.115.6
  uvicorn>=0.34.0
  ```

---

## 10. psycopg2-binary — verze na macOS ARM

- `psycopg2-binary==2.9.10` není dostupný pro macOS ARM (Apple Silicon).
- Řešení: downgrade na `psycopg2-binary==2.9.9`.

---

## 11. YouTube API — Python 3.9 type hints

- Python 3.9 nepodporuje union type hint syntax `str | None` (tato syntax vyžaduje Python 3.10+).
- Error při runtime nebo import.
- Řešení: odstraň return type annotace nebo použij `Optional[str]` z `typing`:
  ```python
  from typing import Optional
  def foo() -> Optional[str]:
      ...
  ```

---

## 12. RSS — The Old Reader API

### User-Agent blokován
- `ClientLogin` endpoint blokuje Python `urllib` default User-Agent (`python-urllib/3.x`).
- Přidej header: `"User-Agent": "BrogiASIST/1.0"` ke všem requestům.

### Správný endpoint pro stream
- Správně: `GET /reader/api/0/stream/contents`
- Špatně: `/reader/api/0/stream/contents/user/-/state/...` — různé varianty nefungují konzistentně.

### Categories v response
- `categories` v item response jsou **strings**, ne dict.
- Správné čtení: `item.get("categories", [])` vrátí list stringů.

---

## 13. MantisBT — datum filter při prvním importu

- Mantis issues mohou mít `date_submitted` nebo `last_updated` starší než aktuální filter window.
- Při prvním importu scheduler filtruje jen posledních N hodin → starší issues se neimportují.
- Řešení: první import spusť bez date filtru (flag `--full` nebo ekvivalent), pak scheduler filtruje normálně.

---

## 14. OmniFocus Bridge — launchd autostart

- Apple Bridge musí běžet na Macu **mimo Docker** (Apple API přístup).
- Autostart bez restartu systému: launchd LaunchAgent.

### Soubor
```
~/Library/LaunchAgents/cz.brogiasist.apple-bridge.plist
```

### Klíčové parametry plist
```xml
<key>KeepAlive</key><true/>
<key>RunAtLoad</key><true/>
```

### Aktivace bez restartu
```bash
launchctl load ~/Library/LaunchAgents/cz.brogiasist.apple-bridge.plist
```

### Restart / stop
```bash
launchctl unload ~/Library/LaunchAgents/cz.brogiasist.apple-bridge.plist
launchctl load   ~/Library/LaunchAgents/cz.brogiasist.apple-bridge.plist
```

---

## 15. iCloud IMAP — App-specific password

- iCloud **vyžaduje** App-specific password — běžné iCloud heslo pro IMAP nefunguje.
- Generování: [appleid.apple.com](https://appleid.apple.com) → Security → App-specific passwords.
- Formát: `xxxx-xxxx-xxxx-xxxx` (4 skupiny po 4 znacích).
- Heslo ulož do konfigurace / `.env`, nikdy do kódu.

---

---

## 16. IMAP STORE flag — quoting a závorky

### Problém: `BAD Parse Error` při STORE na iCloud
- `m.uid("STORE", uid, "+FLAGS", "\\Seen")` **selže na iCloud** s `BAD Parse Error`.
- Totéž se projeví i na jiných striktních serverech.
- **Správně**: `m.uid("STORE", uid, "+FLAGS", "(\\Seen)")` — závorky kolem flag listu jsou povinné dle RFC, iCloud je vyžaduje.
- Gmail toleruje obě formy, iCloud nikoliv.

### Problém: `BAD Parse Error` při MOVE na folder s mezerou
- `m.uid("MOVE", uid, "Deleted Messages")` — bez uvozovek selže s `BAD Parse Error`.
- **Správně**: `m.uid("MOVE", uid, '"Deleted Messages"')` — embedded uvozovky v Python stringu.
- Obecné pravidlo: každý název IMAP složky s mezerou musí být obalený uvozovkami:
  ```python
  def _imap_folder(name: str) -> str:
      if " " in name and not name.startswith('"'):
          return f'"{name}"'
      return name
  ```
- Toto platí pro MOVE, COPY i SELECT.

### Stav v kódu
- `imap_actions.py`: funkce `_imap_folder()` použita v `_uid_move()` a `mark_read()`.
- `backfill_spam_read.py`: stejná funkce.

---

## 17. IMAP — hledání emailů přes Message-ID vs UID

### Kdy použít UID (imap_uid z DB)
- Rychlé, spolehlivé — pokud email nebyl přesunut.
- Selže pokud: email byl přesunut jinam (UID v INBOX se liší od UID po přesunu).
- Gmail: UID je per-label (INBOX UID ≠ All Mail UID ≠ Promotions UID).
- Strategie: zkus UID v uloženém folderu, fallback na Message-ID search.

### Kdy použít Message-ID (source_id z DB)
- Spolehlivé přes přesuny — Message-ID se nemění.
- Pomalejší (server musí skenovat hlavičky).
- Nutné pokud email byl přesunut z INBOX (jiná UID).
- **Správné volání na iCloud**: `m.uid('SEARCH', None, 'HEADER', 'Message-ID', mid)` (separate args).
- **Nepoužívej** string form: `m.uid('SEARCH', None, f'HEADER Message-ID "{mid}"')` → BAD na iCloud.
- Synology: SEARCH HEADER vrací prázdný výsledek — pravděpodobně nepodporováno.

### Hybridní strategie (doporučená)
```python
uid = _find_by_uid(m, imap_uid, folder_db)  # rychlý pokus
if not uid:
    uid, folder = _find_by_message_id(m, source_id, host)  # fallback
```

---

## 18. Dashboard ↔ Scheduler — cross-container komunikace

### Proč
- Dashboard (port 9000) a Scheduler (port 9001) jsou separátní Docker kontejnery.
- IMAP akce (mark_read, move_to_trash) musí běžet v Scheduleru (kde jsou IMAP credentials a kód).
- Dashboard nemůže volat IMAP přímo.

### Řešení: proxy route na Dashboardu
- Dashboard má route `POST /api/ingest/email/{id}/action/{action}`.
- Tato route proxuje request na `http://brogi_scheduler:9001/email/{id}/action/{action}`.
- Scheduler má tento endpoint v `api.py`.
- JS v šabloně volá `fetch('/api/ingest/email/${id}/action/${action}', {method:'POST'})`.
- Nikdy nevolej Scheduler API přímo z frontendu (jiný port, CORS problémy).

### Env proměnná
```
INGEST_URL=http://brogi_scheduler:9001   # v dashboard kontejneru
```

---

## 19. Jinja2 template — sloupec `action_payload` vs `raw_payload`

### Chyba: tiché selhání přes `except Exception: pass`
- V `dashboard/main.py` byl dotaz používající neexistující sloupec `raw_payload` (správně: `action_payload`).
- `psycopg2` hodil výjimku, ale `except Exception: pass` ji spolkl → `emails = []` → prázdná stránka /ukoly.
- **Poučení**: nikdy nepoužívej `except Exception: pass` v DB dotazech. Vždy loguj:
  ```python
  except Exception as _e:
      logging.getLogger("ukoly").error(f"Chyba: {_e}")
  ```

---

## 20. Action logging — proč ChromaDB a ne PostgreSQL `actions` tabulka

### Stav 2026-04-25
- PostgreSQL `actions` tabulka existuje (sql/001_init.sql), ale **kód do ní nezapisuje** — je rezervovaná pro budoucí confirmation workflow (pending → confirmed → executed).
- Skutečný action log je v **ChromaDB collection `email_actions`** přes `chroma_client.store_email_action()`.
- Volá se po každé akci v `imap_actions.py` (`mark_read`, `move_to_trash`, `move_to_brogi_folder`) a v `telegram_callback.py` / `api.py`.
- Účel: nejen log, ale primárně **learning** — `find_repeat_action()` před notifikací zkouší pattern match (≥3 podobné emaily s cosine ≤0.15 → auto-akce bez TG potvrzení).

### Důsledky pro debugging
- Pokud chceš auditovat akce, **nehledej v `actions` tabulce** — je prázdná.
- Stav v PG drží `email_messages.status` (`new`/`classified`/`reviewed`/`unsubscribed`) + `folder` + `human_reviewed`.
- IMAP `\Seen` flag autoritativní zdroj = IMAP server, ne DB. Nelze v DB SQL dotazem zjistit "kolik je nepřečtených".

### Dead columns v `email_messages`
- `processed_at` — nikdy se nezapisuje. Logika přechází přes `status` + `folder` + `human_reviewed`.
- `raw_payload` neobsahuje `seen` flag.

---

## 21. IMAP transient connect errors — auto-recovery

### Co se v lozích objevuje
```
[ERROR] [account] Chyba: [Errno -3] Try again — reconnect za 30s
[ERROR] [account] Chyba: command: LOGIN => socket error: EOF — reconnect za 30s
[ERROR] [account] Chyba: EOF occurred in violation of protocol (_ssl.c:2437) — reconnect za 30s
```

### Co to znamená
- `[Errno -3] Try again` = transient DNS resolve failure z Docker kontejneru.
- `EOF in violation of protocol` = TLS handshake ztratil spojení (často shodný moment napříč všemi účty → síťový blip).
- `socket error: EOF` při LOGIN = server zahodil spojení (rate limit / restart serveru).

### Reakce systému
- Scheduler má auto-reconnect 30s — IDLE se znovu obnoví během 5–15 minut.
- Není potřeba zásah, **pokud chyba opakovaně blokuje konkrétní účet déle než hodinu**.
- Při dlouhodobém výpadku konkrétního účtu: zkontroluj `imap_status` tabulku (per-account health).

### Důsledky pro DB obsah
- Pokud byl účet dlouho odpojený a měl IDLE-only fetch → nové emaily se mohou zachytit až při backup scanu (30min).
- Tichý INBOX (např. `brogi@`, `servicedesk@`) ≠ broken ingest. Ověř nejdřív v Mail.app jestli tam vůbec něco přichází.

---

## 22. Konvence pojmenování účtů — `mailbox` v DB

- Sloupec `email_messages.mailbox` obsahuje **email adresu** (např. `dxpavel@gmail.com`), ne display name z Mail.app.
- Mail.app často zobrazuje účty pod přezdívkami:
  - `BrogiMAT email` = `brogi@dxpsolutions.cz`
  - `ZÁMEČNICTVÍ Rožďálovice` = `zamecnictvi.rozdalovice@gmail.com`
- Při porovnání Mail.app ↔ DB **vždy mapuj přes adresu**, ne přes display name.

---

---

## 23. DB row-level lock contention v `_email_action` — KRITICKÁ PAST (2026-04-25)

### Symptom
- Každý klik na akční tlačítko (TG nebo WebUI) visí nekonečně (timeout 30–60s).
- `skip` funguje, ostatní akce ne.
- V `pg_stat_activity`: jedno připojení `idle in transaction` + druhé čeká na UPDATE stejného řádku.

### Příčina
`_email_action()` původně: otevřela `conn1`, udělala `UPDATE email_messages` bez commitu, pak zavolala `move_to_brogi_folder()` / `move_to_trash()`. Tyto funkce otevírají **vlastní** `conn2` a v `_update_db_folder()` volají další `UPDATE` na stejný řádek. `conn2` blokuje na row-locku z `conn1`. `conn1` čeká až `move_to_*` vrátí → **uváznutí**.

### Oprava
Pořadí v `_email_action` (viz `telegram_callback.py`):
1. Bridge call (OF/REM/NOTE) — pokud selže, return early
2. `conn.commit()` a `conn.close()` — uvolnit row-lock **před** IMAP
3. `move_to_brogi_folder()` / `move_to_trash()` — otevírají vlastní conn, mohou UPDATE volně

### Diagnostika
```bash
docker exec brogi_postgres psql -U brogi -d assistance -c "
SELECT pid, state, age(now(), xact_start) AS xact_age, left(query, 100) AS query
FROM pg_stat_activity WHERE datname='assistance' AND state != 'idle';"
```
Pokud vidíš `idle in transaction` + `active` na stejném řádku → tohle je ten problém.

```bash
# Nouzové řešení — zabij stuck transakce:
docker exec brogi_postgres psql -U brogi -d assistance -c "
SELECT pg_terminate_backend(pid) FROM pg_stat_activity
WHERE datname='assistance' AND state='idle in transaction';"
```

---

## 24. Docker kontejner nedostane změny automaticky (2026-04-25)

### Situace
Docker Compose pro `scheduler` **nemá bind mount** pro `services/ingest/` — zdrojové soubory jsou nakopírované do image při `docker build`. Úprava souboru na hostu se do běžícího kontejneru **nepropaguje**.

### Rychlá oprava (pro testování)
```bash
docker cp services/ingest/telegram_callback.py brogi_scheduler:/app/telegram_callback.py
docker restart brogi_scheduler
```

### Správné řešení pro produkci
Přidat bind mount do `docker-compose.yml`:
```yaml
scheduler:
  volumes:
    - ./services/ingest:/app   # zdrojové soubory live-mounted
    - ./logs:/app/logs
```
Nebo použít `docker compose up -d --build scheduler` po každé změně.

### Jak zjistit stáří souboru v kontejneru
```bash
docker exec brogi_scheduler stat -c "%y" /app/telegram_callback.py
# Porovnej s lokálním: stat -f "%Sm" services/ingest/telegram_callback.py
```

---

## 25. TG callback offset — persistentní v DB (2026-04-25)

### Stav
- Offset uložen v tabulce `config` (key=`tg_callback_offset`) po každém zpracovaném update.
- Při restartu scheduleru se offset načte z DB → žádné ztracené callbacks.
- Fallback: pokud `config` tabulka selže, offset=0 (emaily se znovu přepošlou jako duplicate).

### Kde v kódu
- `telegram_callback.py`: `_load_offset()`, `_save_offset()`, `run_callback_loop()`.

---

## 26. Google Calendar pozvánek — špatná klasifikace (2026-04-25)

### Symptom
Emaily ve tvaru `Invitation: Název události @ datum (dxpavel@me.com)` od Google Calendar jsou klasifikovány jako `NABÍDKA` (ai_confidence 0–1, ale zjevně chybná).

### Příčina
AI (Llama3.2) nemá v seznamu typů `POZVÁNKA` ani `KALENDÁŘ`. Vidí slovo *Invitation* + strukturu a zvolí `NABÍDKA` jako nejbližší match.

### Řešení (zatím ne implementováno)
1. **classification_rules**: přidat rule `subject ILIKE 'Invitation:%' → typ=POTVRZENÍ` (nebo ÚKOL).
2. **Prompt engineering**: přidat instrukci do Llama promptu.
3. **Nový typ POZVÁNKA**: rozšířit enum a klasifikační logiku.

---

---

## 27. Claude API — httpx bez SDK (2026-04-25)

### Situace
Potřebujeme volat Anthropic API z Docker kontejneru kde není nainstalován `anthropic` Python SDK (není v requirements.txt). Přidání SDKs vyžaduje rebuild image.

### Řešení
Volání přes `httpx` (již dostupný):
```python
r = httpx.post(
    "https://api.anthropic.com/v1/messages",
    headers={
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    },
    json={"model": "claude-haiku-4-5", "max_tokens": 128,
          "messages": [{"role": "user", "content": prompt}]},
    timeout=30,
)
text = r.json()["content"][0]["text"]
```
Response text pak parsuj jako JSON (find `{` / rfind `}`) stejně jako u Llamy.

### Env proměnná
`ANTHROPIC_API_KEY` musí být v `.env` — scheduler používá `env_file: .env`.
**Pozor**: `docker restart` nepřečte `.env` znovu — nutný `docker compose up -d --force-recreate scheduler`.
Po force-recreate se ztratí všechny `docker cp` soubory — nutné znovu zkopírovat!

---

## 28. docker compose force-recreate maže docker cp soubory (2026-04-25)

### Situace
Po `docker compose up -d --force-recreate scheduler` se kontejner vytvoří znovu z původního image.
Všechny soubory nakopírované přes `docker cp` se ztratí — kontejner má čistý stav z image.

### Pravidlo
Pořadí musí být vždy:
1. `docker compose up -d --force-recreate scheduler` (kvůli env_file)
2. `docker cp <soubor> brogi_scheduler:/app/<soubor>` (pro každou změnu)

Nebo lépe: přidat bind mount `./services/ingest:/app` do docker-compose.yml (pak stačí `restart`).

---

## 29. ChromaDB — editace záznamu vyžaduje delete + upsert (2026-04-25)

### Situace
ChromaDB HTTP API neumí editovat metadata existujícího záznamu bez přepsání embeddingu.

### Řešení
1. `GET /collections/{col_id}/get` s `ids=[id]` a `include=["embeddings","documents","metadatas"]`
2. Extrahuj embedding + document
3. `POST /collections/{col_id}/delete` s `ids=[id]`
4. `POST /collections/{col_id}/upsert` se stejným embedding + document + nová metadata

Pokud chybí embedding v responsi, zkontroluj `include` parametr — default nemusí vrátit embeddingy.

---

## 30. UPSERT v PostgreSQL — detekce INSERT vs UPDATE (2026-04-25)

### Situace
Chceme vědět jestli UPSERT vytvořil nový záznam nebo jen aktualizoval existující.

### Řešení
```sql
INSERT INTO email_messages (...)
VALUES (...)
ON CONFLICT (source_id) DO UPDATE SET ...
RETURNING id, (xmax = 0) AS is_new
```
- `xmax = 0` → nový INSERT
- `xmax != 0` → UPDATE existujícího záznamu

---

## 31. apple_contacts — prázdné emails[] pole (2026-04-25)

### Situace
Kontakt Lukáš Lahoda má v `apple_contacts` tabulce `emails: []` (prázdné pole).
`_is_contact()` dotaz matchuje pouze kontakty s neprázdnými emails.
Výsledek: Lahoda nebyl zachycen automatickým whitelistem.

### Příčina
AddressBook sqlite může mít kontakty bez emailové adresy (pouze telefonní číslo, nebo email uložen jinak v iCloud).

### Dopad
Auto-cleanup Chroma spam záznamů přeskočil Lahodu.
Tři Lahoda spam záznamy musely být smazány ručně přes Chroma HTTP API.

### Řešení (budoucí)
Zvažit rozšíření `_is_contact()` o fuzzy match na jméno (first_name + last_name), pokud je emails[] prázdný.

---

## 32. OmniFocus 4 — fyzické attachmenty přes scripting NEJDOU (2026-04-26)

### Symptom
Pokus o `make new attachment` přes JXA i AppleScript skončí chybou:
```
JXA:         Can't get object.
AppleScript: OmniFocus got an error: Can't make or move that element into that container.
```

### Co bylo testováno (kaskáda)
1. JXA `task.attachments.push(of2.FileAttachment({file: Path(fp)}))` → `Can't get object`
2. JXA `of2.make({new: 'fileAttachment', at: target.attachments, withProperties: {file: Path(fp)}})` → totéž
3. AppleScript `make new attachment with properties {file name:POSIX file "..."}` → `Can't make or move that element into that container`
4. NSFileWrapper přes ObjC bridge (původní experiment) → tichý fail

### Závěr
**Klasické scripting API (JXA/AppleScript dictionary) v OF 4 nepřijímá nové file attachmenty.** Není to bug v kódu — OF API to nedovoluje. Pravděpodobně je `attachments` element v dictionary read-only nebo make/append není podporován pro tento typ.

### Dostupné alternativy
| Cesta | Stav | Poznámka |
|---|---|---|
| **D — file:// linky v note** | ✅ aktuální řešení | 1 click → otevře v Náhledu |
| **E — Omni Automation (OmniJS)** | ⚠️ neimplementováno | JS běžící uvnitř OF, moderní API; vyžaduje plugin schválení + možná narazí na sandbox pro `~/Desktop/BrogiAssist/` |
| **F — OmniFocus URL scheme** | ❌ dead-end | `omnifocus:///add?...` neumí attachment payload |

### Aktuální chování (1.1)
Apple Bridge `/omnifocus/add_task` má kaskádu C → B → links_only. C+B se zkoušejí, oba selžou, končí na `attach_method=links_only`. Response obsahuje `attach_errors` pro audit.

---

## 33. Base64 přílohy přes JSON — funkční pattern pro DEV i PROD (2026-04-26)

### Problém
Přílohy emailů se musí dostat ze scheduleru (Linux Docker container, BrogiServer na PROD) do Apple Bridge (macOS proces na Apple Studio na PROD). Sdílený filesystem mezi stroji není (různé sítě, různé OS). Bind mount funguje jen na DEV (1 stroj).

### Řešení (v 1.1)
- Scheduler čte soubor přes container path (po replace `Mac path → /app/attachments`)
- Encodeuje base64 (`base64.b64encode(data).decode("ascii")`)
- Posílá v `POST /omnifocus/add_task` jako pole `files: [{filename, content_base64, size_bytes}]`
- Bridge dekóduje a ukládá do `~/Desktop/BrogiAssist/<email_id>/<filename>`

### Limity (záměrné)
- Per-soubor: **50 MB** (= `_MAX_ATTACHMENT_SIZE` v `ingest_email.py`)
- Per-task: **100 MB** (rozumný JSON payload — větší by zatížil scheduler i bridge)
- Soubory přesahující limit jsou přeskočeny + log warning
- Base64 zvětší payload ~33 % → 100 MB binary = ~133 MB JSON

### Funkční na (testováno 2026-04-26)
- **DEV**: scheduler v Dockeru → host.docker.internal:9100 → bridge → ~/Desktop/BrogiAssist/ ✅
- **PROD plánováno**: scheduler na BrogiServer → 10.55.2.117:9100 → bridge na Apple Studio → ~/Desktop/BrogiAssist/

### Důležité pro fail-recovery
Bridge vrací `attachments_saved` v response. Scheduler ho neukládá (loguje do `OF created: status=200`). Při debug situaci ověřit `attachment_dir` přímo na disku (`ls ~/Desktop/BrogiAssist/<email_id>/`).

---

## 34. file:// URL pro non-ASCII cesty — `urllib.parse.quote` povinné (2026-04-26)

### Problém
file:// URL s českými znaky (`ř`, `Č`, `ý`) v cestě nebo názvu souboru macOS odmítne otevřít — kliknutí v OmniFocus / Mail / TextEdit nic neudělá nebo otevře "URL not found".

### Špatně (původní kód)
```python
# Řeší jen mezery, non-ASCII zůstává nevalidní
url = f"file://{path.replace(' ', '%20')}"
```

### Správně (1.1)
```python
import urllib.parse
url = f"file://{urllib.parse.quote(path, safe='/')}"
# /Users/pavel/Desktop/.../elektřina.pdf
# →
# /Users/pavel/Desktop/.../elekt%C5%99ina.pdf
```

`safe='/'` zachová separátory cesty, vše ostatní (mezery, diakritiku, speciální znaky) zakóduje jako UTF-8 percent-encoded.

### Příklad
```
ř   → %C5%99
Č   → %C4%8C
ý   → %C3%BD
mezera → %20
```

---

## 35. macOS fork() bug v multi-threaded Python — `os.posix_spawn()` je jediný spolehlivý fix (2026-04-26)

### Co se stalo
Apple Bridge na PajaAppleStudio náhodně padal s `EXC_BAD_ACCESS (SIGSEGV)`
v `Network.framework atfork hook` (cca 1× za 15 min, 2× za den). Stack trace:

```
*** multi-threaded process forked ***
crashed on child side of fork pre-exec
0  libsystem_trace      _os_log_preferences_refresh + 56
2  libnetworkextension  NEFlowDirectorDestroy + 64
4  Network              nw_settings_child_has_forked() + 296
5  libsystem_pthread    _pthread_atfork_child_handlers + 76
6  libsystem_c          fork + 112
7  _posixsubprocess     do_fork_exec + 68
```

uvicorn (FastAPI) má vlákna; `subprocess.run()` volá `fork()`+`exec()`; v child
po fork() Apple's atfork hooks (Network.framework) selhávají při refreshi
log preferences → SIGSEGV.

### Co nefungovalo
- **Workaround #1**: env var `OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES` v launchd
  plistu. Apple deprecated, na **macOS 26.4.1 ho ignoruje**. Nasazeno 19:33,
  další crash o 15 minut později.
- Restart `tccd`, restart Bridge — žádný efekt.

### Proper fix (FUNGUJE)
Nahradit `subprocess.run()` za `os.posix_spawn()` v `run_applescript`/`run_jxa`
wrapperech v `services/apple-bridge/main.py`:

```python
def _spawn_osascript(args, timeout):
    stdout_r, stdout_w = os.pipe()
    stderr_r, stderr_w = os.pipe()
    file_actions = [
        (os.POSIX_SPAWN_DUP2, stdout_w, 1),
        (os.POSIX_SPAWN_CLOSE, stdout_r),
        (os.POSIX_SPAWN_DUP2, stderr_w, 2),
        (os.POSIX_SPAWN_CLOSE, stderr_r),
    ]
    pid = os.posix_spawn('/usr/bin/osascript', args, os.environ, file_actions=file_actions)
    # ... pipe read + waitpid
```

`posix_spawn()` je **atomický syscall** — nedělá fork() + exec() postupně,
neprovádí kopii address space, **atfork hooks se nevolají** → bug se neprojeví.

### Verifikace
50 requestů na `/omnifocus/tasks` (5 paralelních osascript subprocesů),
21 minut zátěže lokálně → **0 nových crash reportů**. Předtím by Bridge
spadl několikrát.

### Lekce
- **Apple od macOS Catalina nedoporučuje fork() v multi-threaded apps.**
  Pokud Python aplikace má threadpool (uvicorn/Flask) a volá subprocess,
  riziko že atfork hooks zlomí child proces.
- `OBJC_DISABLE_INITIALIZE_FORK_SAFETY` je **deprecated** — Apple ho v některém
  release přestal honorovat (jistě v 26.x). Nespoléhat na něj.
- `os.posix_spawn()` je Python 3.8+ řešení. Nízkoúrovňové (file_actions pro
  pipes), ale spolehlivé.
- Detail v `docs/BUGS.md` BUG-008.

---

## 36. macOS TCC (Full Disk Access) — launchd-spawned procesy NEDĚDÍ FDA z user FDA seznamu (2026-04-26)

### Co se stalo
Apple Bridge přes launchd potřeboval číst `~/Library/Application Support/AddressBook/`
(Apple Contacts sqlite databáze) → `PermissionError: Operation not permitted`.

Pavel přidal **Python.app do System Settings → Privacy & Security → Full Disk
Access** (toggle ON, přesná cesta `/opt/homebrew/Cellar/python@3.11/3.11.15/...
/Python.app`). Bridge restartován přes `launchctl unload + load`. **Stále
PermissionError.**

Sequence diagnostiky:
- Smazat oba Python entries → re-add přes Cmd+Shift+G s přesnou cestou → restart Bridge → fail
- `sudo killall tccd` (TCC daemon reset) → restart Bridge → **fail**
- Změnit plist aby spouštěl Python přímo (bez bash run.sh wrapper) → fail

### Příčina
**TCC FDA permissions per-process zohledňují responsible parent app**, ne
přímý executable. Pro launchd-spawned LaunchAgents je responsible parent =
launchd (system process), který **nemá FDA**, a permission **se nedědí**
z user FDA seznamu.

Když Pavel spustil **stejný Python skript z Terminal.app** na Apple Studio
(přes ssh + manuálně), permission projde — Terminal.app má FDA + ten Python
proces je child Terminalu = dědí FDA.

### Workaround / pivot
**Apple Contacts má separátní permission "Automation" (AppleEvents)** —
nezávislé na FDA. JXA volání `Application('Contacts').people()` projde přes
Automation permission (Pavel dialog při prvním volání → Allow).

Apple Bridge `/contacts/all` přepsán z `sqlite3` direct read na **JXA**:

```python
script = '''
const contacts = Application('Contacts');
contacts.includeStandardAdditions = false;
const groupMap = {};
for (let g of contacts.groups()) { ... }
const people = contacts.people();
// per kontakt: id, firstName, lastName, organization, groups[]
'''
contacts_data = run_jxa(script, timeout=240)
```

Trvá ~100s pro 1180 kontaktů (5x víc než sqlite), ale **nepotřebuje FDA**.

### Lekce
- Pro launchd-spawned procesy je **FDA cesta zlomená** na macOS 26.x. Pokud
  Bridge potřebuje číst chráněné cesty (`~/Library/Application Support`,
  `~/Library/Mail`, atp.), použít přes Apple-poskytnuté **AppleEvents API**
  (Notes, Contacts, Calendar, Reminders, Mail, OmniFocus) — Apple je
  spravuje přes "Automation" permission, kterou launchd-spawned procesy
  získat můžou.
- **Direct sqlite read** na chráněné DB **funguje JEN když process má FDA**
  — což je bezpečné jen pro Terminal.app + child procesy. Bridge přes launchd
  ne.
- Apple Bridge nyní udržuje OBA endpointy: `/contacts/all` (JXA, primární)
  a `/contacts/all_sqlite` (legacy fallback s `no_fda` graceful degrade).
- Detail v `docs/BUGS.md` poznámkách k BUG-008 a v `services/apple-bridge/main.py`
  komentářích.

---

## 37. JXA per-property volání jsou drahé — `properties()` batch + omezený scope (2026-04-26)

### Co se stalo
První implementace JXA `/contacts/all` volala per-kontakt:
```js
const props = {
    id: p.id(),
    first: p.firstName(),
    last: p.lastName(),
    org: p.organization(),
    emails: p.emails().map(e => ({label: e.label(), value: e.value()})),
    phones: p.phones().map(p => ({label: p.label(), value: p.value()})),
    modified_at: p.modificationDate()?.toISOString(),
    groups: groupMap[p.id()] || [],
};
```

Pro 1180 kontaktů × ~10 bridge calls = **11 800 JXA bridge volání** → run_jxa
timeout 90s nestačil, request timeoutoval po **101 sekundách s žádnou odpovědí**.

### Optimalizace
1. **Skupiny získat jako mapping** mimo per-person loop — 1× `contacts.groups()`,
   per skupina 1× `g.people().map(p => p.id())`. Max 19 calls (počet skupin).
2. **Per-kontakt jen 4 calls**: `id`, `firstName`, `lastName`, `organization`.
   Vynechat: emails, phones, modificationDate (drahé, méně potřebné — máme
   z dřívějších sqlite ingestů v PostgreSQL).
3. **try/catch per kontakt** — některé kontakty mohou mít poškozená data
   (např. `firstName` throws na deleted person), nezpůsobit fail celého requestu.
4. **timeout 240s** v `run_jxa(script, timeout=240)` — bezpečná rezerva.

Výsledek: 1180 kontaktů za **~101s** (5–6 OK, 21 fail — ne JXA, ale neúplná
data v Contacts.app pro některé kontakty). Pro náš účel (groups jako
orthogonal signál) dost dobré.

### Lekce
- **JXA bridge calls jsou drahé** (~50/s typicky). Pro batch operations
  (1000+ záznamů) plánovat per-property volání pečlivě. Lépe:
  - 1× `collection.<property>()` (vrátí array hodnot pro všechny záznamy)
  - JOIN přes index (i v JS poli)
- Per-property `whose()` queries v JXA jsou pomalé — `flattenedTasks.whose({completed: false})`
  pro 466 OF tasků je rozumné (1× call), ale pro 1180 kontaktů × 10 properties už
  je to limit.
- Některé Contacts.app kontakty mají poškozená/chybějící data → `try/catch`
  per záznam je nutné, jinak fail celé operace.
- Kontaktové **emails/phones lze získat samostatným endpointem** (`/contacts/full?id=X`)
  pokud potřebné — refresh on-demand.
- Detail v `services/apple-bridge/main.py:contacts_all()`.

---

## 38. Silent auto-spam = race condition past — vždy human-in-the-loop pro destruktivní akce (2026-04-27)

### Incident
2026-04-27 14:05:47 logy ukázaly:

```
[INFO] move_to_trash OK: dxpavel@icloud.com uid=46122 → Deleted Messages
[INFO] SPAM (auto trash, 100%): Re: dane 2025
[INFO] Klasifikováno: firma=PRIVATE typ=ÚKOL spam=false (100%)
```

Email od `krouzecka@volny.cz` (Pavlova účetní, kontakt v Apple Contacts.app, ale
s emailem typu „Siri found in Mail" které JXA nevidí → `ingest_contacts` ho
nezahrnul → `_is_contact()` whitelist nematchnul). Llama označila spam
confidence 1.0 → silent move_to_trash. Vzápětí stejný email znovu klasifikován
jako typ=ÚKOL spam=false, ale akce už proběhla (klasický race condition v
`classify_emails.py`).

### Root cause kandidáti (zatím nevyřešeno)
- Souběh ingest IDLE push + scan job — stejný email zpracován dvakrát s různými
  výstupy Llamy (deterministická Llama není 100%).
- DB-level: nedostatečný `LOCK` / `FOR UPDATE SKIP LOCKED` při výběru `status='new'`
- Apple Contacts whitelist neexponuje emaily typu „Siri found in Mail" → falešně
  negativní `_is_contact()` pro Pavlovu účetní

### Dočasný fix
`classify_emails.SPAM_AUTO_THRESHOLD = 2.0` (= podmínka `confidence > 2.0` nikdy
nesplněna → silent auto-trash neběží). Učení v Chromě (`store_email_action`,
`find_repeat_action`) dál funguje, jen bez auto-execute.

Pavel klikne 2spam / 2del ručně na TG.

### Poučení
- **Silent destruktivní akce = nepřípustné** dokud není 100% zajištěna idempotence
  a deterministická klasifikace.
- **Auto-apply z Chromy též vypnut** (commit 2837dae) — místo toho se vzor
  zobrazí jako návrh (`⭐ Navrženo: 2X (NN%) ⭐`) a Pavel klikne.
- **Pattern**: pro každou novou „auto" funkci se zeptat: „co se stane, když
  klasifikace (Llama / Chroma / heuristika) je flipnutá v dalších 5s?"
  Pokud odpověď zahrnuje „mail je v Trash", potřebujeme TG zprávu místo silent
  execute.

---

## 39. `Auto-Submitted: auto-generated` ≠ bounce — RFC 3464 vs běžné notifikace (2026-04-27)

### Incident
MantisBT issue notifikace [HOSPODARY 0000255/0000256] od
`servicedesk@dxpsolutions.cz` dostala TYP=ERROR. Důvod: pravidlo `header_bounce`
v `decision_rules` matchovalo header `Auto-Submitted: auto-generated`, který má
**každá** systémová notifikace (MantisBT, GitHub, monitoring), ne jen reálné
DSN bounce reporty.

### Standard
RFC 3464 (Delivery Status Notifications) definuje:

```
Content-Type: multipart/report; report-type=delivery-status; boundary="..."
```

Toto má **POUZE** reálný bounce. `Auto-Submitted: auto-generated` má cokoliv
co není odpověď člověka.

### Fix
`sql/013_decision_rules.sql` rule `header_bounce`:

```sql
-- před: condition matchovala Auto-Submitted contains 'auto-generated'
-- po:   condition matchuje Content-Type contains 'multipart/report'
```

Plus DB UPDATE na PROD VM 103 (rule + dva falešně klasifikované emaily reset
typ=NULL, status='new', human_reviewed=FALSE) — ty pak prošly znova přes
opravený engine.

### Poučení
- **Header detekce v decision_rules vyžaduje znalost RFC** — `Auto-Submitted`
  je široký, `multipart/report` je úzký a deterministický.
- Po opravě: skutečné bounce DSN dostávají TYP=ERROR (≥95 % bounce trafficu),
  MantisBT/GitHub/monitoring jdou na `ai_fallback` (Llama → typicky NOTIFIKACE).
- CLAUDE.md sekce 12 (gotchas) přidán řádek s tímto rozdílem.

---

## Co ještě nebylo řešeno / TODO

- **iMessage ingest** — bridge endpoint naplánován, ingest skript a DB tabulka chybí
- **Calendar Full Disk Access na PROD** — na BrogiServer (Apple Studio) bude potřeba explicitně udělit Full Disk Access pro bridge proces
- **ChromaDB query layer** — `find_repeat_action` běží před notifikací; další vektorové vyhledávání (semantic search nad maily) zatím nepoužito
- **PROD deployment** — BrogiServer (Apple Studio) není nakonfigurován; celý stack běží jen na DEV
- **BrogiASIST složky na Forpsi** — na Forpsi/Synology nejsou vytvořeny BrogiASIST/* složky; emaily se přesouvají jen do Trash
- **`actions` tabulka** — confirmation workflow (pending → confirmed → executed) není implementován; tabulka je placeholder
- **`email_messages.processed_at`** — dead column; buď začít zapisovat při akci, nebo dropnout při příští migraci
- **Apple Bridge notes/add JXA** — escaping speciálních znaků v body textu; Python f-string interpolace rozbije JS string → SyntaxError 500. Opravit pomocí `json.dumps(body)`.
- **docker-compose bind mount** — přidat `./services/ingest:/app` volume pro scheduler (jinak `docker cp` + force-recreate po každé změně env)
- **claude_sender_verdicts** — zatím bez TTL / expiry; verdikt může být zastaralý pokud se odesílatel změní z legitimního na spam. Zvážit `verified_at < NOW() - INTERVAL '90 days'` jako refresh trigger.
- **apple_contacts kontakty bez emailu** — `_is_contact()` nefunguje pro kontakty s prázdným emails[]. Zvážit fallback na jméno.

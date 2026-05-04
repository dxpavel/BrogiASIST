# CLAUDE.md — BrogiASIST projektová pravda

> **Autoritativní pravda o tomto projektu.** Tento dokument se načítá automaticky
> na startu každé Claude Code session. Pokud si Claude pamatuje něco jiného
> z **memory** (`~/.claude/projects/.../memory/`), **CLAUDE.md vyhrává**.
>
> Když edituješ tento soubor a commitneš, **další session si přečte aktuální
> verzi automaticky** — žádný upload, žádné mazání memory.

---

## 0. POVINNÉ PRAVIDLO PRO CLAUDE: NIKDY NETVRDÍŠ NEZNÁMÉ JAKO ZNÁMÉ

**Před tvrzením o realitě (co kde běží, jaké jsou IPs, co je v gitu, co dělá kód, co je v DB) MUSÍŠ ověřit:**

| Co tvrdit chceš | Jak ověřit (povinné) |
|---|---|
| „PROD běží na X" / „Apple Bridge je tam" | `ssh pavel@10.55.2.231 "docker compose ps"` nebo `curl -sm 5 http://10.55.2.117:9100/health` |
| „Branch / poslední commit je..." | `git log -1 --oneline`, `git status`, `git branch --show-current` |
| „V kódu se to dělá takto..." | `Read` na konkrétní soubor + řádek, neříkej z paměti |
| „V DB je..." | `docker exec brogiasist-postgres psql -U brogi -d assistance -c "..."` |
| „V dokumentaci je..." | `Read` na konkrétní `docs/X.md`, neparafrázuj z memory |
| „V Chromě je..." | `httpx.get http://chromadb:8000/api/v2/...` přes scheduler container |

**Když nemůžeš ověřit:** řekni explicitně **„neověřeno"** a navrhni jak to ověřit.
NIKDY neříkej „myslím že" ve formě tvrzení. Použij „neověřeno, ověř to ručně"
nebo udělej ověření ty sám.

**Pavlův Asperger to vyžaduje** — fakta nebo nic.

---

## 1. KOMUNIKAČNÍ PRAVIDLA (Pavel — Asperger + ADHD)

> Tohle jsou tvrdá pravidla. Porušení = frustrace.

| Pravidlo | Detail |
|---|---|
| **Strukturovaně, bez keců** | Krátké odpovědi, tabulky, bullet points. Žádné „já si myslím", „možná", „mohlo by být". |
| **Jedna otázka najednou** | Když potřebuješ víc rozhodnutí, polož jedno, počkej, pak další. |
| **Navrhuj před implementací** | UI/architektura: nejdřív navrhni postup → počkej na souhlas → potom implementuj. |
| **Označuj** | 🍏 ok/hotovo · 🍎 problém · 🐒 riziko/postřeh · ⚠️ varování |
| **Žádné autonomní změny** | Reakce na screenshot/komentář ≠ pokyn implementovat. Pokud nejsi 100% jistý že máš pokyn, **zeptej se**. |
| **Před prací čti zdroj** | UI/CSS změna → grep CSS, screenshot, ne hádej. |
| **Před UI implementací** | Navrhni → souhlas → implementuj. Bez výjimky. |
| **Krátké odpovědi** | Pokud nemáš dlouhý důvod psát dlouho, piš krátce. |
| **Příznak chyby = okamžitá akce** | Když Pavel řekne „STOP" / „PAUZA" / vyjadřuje frustraci → zastav, vrať se, ověř, ne pokračuj. |
| **Jazyk** | Česky (občas anglické technické termíny — ok). |

---

## 2. AKTIVNÍ BRANCH + STAV (ověřuj před prací)

```bash
git branch --show-current   # má vrátit '2' (release v2 in progress)
git log -1 --oneline        # poslední commit
git status                  # musí být clean před deploy
```

**Přepokládaný stav (může být zastaralý — VŽDY OVĚŘ):**
- Aktivní branch: `2` (release v2 — Email Semantics v1)
- Stable tag: `v1.1` (commit `ee483ba` na main) — bod návratu
- Tag prehistorie: `0.0.1-initial`, `0.0.1-snapshot`, `0.1.0-snapshot`

**Pokud `git branch --show-current` vrátí jiný branch než `2`, ZEPTEJ SE Pavla** než cokoli udělаš.

---

## 3. PROD INFRASTRUKTURA (autoritativní per `docs/brogiasist-infrastructure-v1.md`)

> ⚠️ **Pokud memory říká „Forpsi VPS" nebo „OS01" — MEMORY LŽE.**
> Stará verze, projekt už byl migrovaný 2026-04-26.

### LAN topologie (10.55.2.0/24)

| Stroj | IP | Role | Přístup |
|---|---|---|---|
| MacBook Pro Pavla | 10.55.2.73 | DEV / Pavlův pracovní stroj | lokálně |
| **Apple Studio** | **10.55.2.117** | **PROD Apple Bridge** (port 9100) | `ssh dxpavel@10.55.2.117` |
| Proxmox pve01 | 10.55.2.201 | Hypervizor pro VM | `ssh root@10.55.2.201` |
| **VM 103 brogiasist** | **10.55.2.231** | **PROD Docker stack** | `ssh pavel@10.55.2.231` |

LAN je propustná, žádný VPN, žádný proxy. **Žádný veřejný expose** (PROD je interní).

### PROD Docker stack na VM 103 (5 kontejnerů)

```
brogiasist-postgres   (PostgreSQL 16, port 5432)
brogiasist-chromadb   (ChromaDB, port 8000)
brogiasist-ollama     (Ollama llama3.2-vision:11b, port 11434)
brogiasist-dashboard  (FastAPI dashboard, port 9000)
brogiasist-scheduler  (APScheduler + IMAP IDLE + TG bot + queue worker, port 9001)
```

Plus `brogiasist-beszel-agent` (monitoring → VM 101 Beszel Hub).

### Apple Bridge na Apple Studio

- Python 3.11.15 (Homebrew) přes launchd
- Plist: `~/Library/LaunchAgents/cz.brogiasist.apple-bridge.plist`
- Spouštěn jako: `/Users/dxpavel/brogiasist-bridge/.venv/bin/python /Users/dxpavel/brogiasist-bridge/main.py`
- **BUG-008 fix:** `os.posix_spawn()` místo `subprocess.run()` (multi-threaded fork crash)
- TCC permissions: Automation pro Contacts/Mail/Calendar/Notes/OmniFocus (přes JXA AppleEvents)
- FDA pro Python.app v System Settings (legacy `/contacts/all_sqlite` to vyžaduje, primary `/contacts/all` JXA ne)

---

## 4. KLÍČOVÉ ENV PROMĚNNÉ

> Reálné hodnoty v `.env` (ne v gitu). Tady struktura — když potřebuješ konkrétní
> hodnotu, **nečti** je z paměti, **přečti** ze souboru přes ssh:
> `ssh pavel@10.55.2.231 "cat ~/brogiasist/.env"`.

```env
# DB
POSTGRES_DB=assistance, POSTGRES_USER=brogi, POSTGRES_PASSWORD=...

# AI
OLLAMA_URL=http://ollama:11434          # ← NE OLLAMA_BASE_URL (legacy chyba)
OLLAMA_MODEL=llama3.2-vision:11b
ANTHROPIC_API_KEY=sk-...

# Apple Bridge (LAN propojení)
APPLE_BRIDGE_URL=http://10.55.2.117:9100  # PROD
# DEV by mělo http://host.docker.internal:9100

# Telegram
TELEGRAM_BOT_TOKEN=8463405339:...
TELEGRAM_CHAT_ID=7344601948

# 9 IMAP účtů: brogi@dxpsolutions.cz, pavel@dxpsolutions.cz, support@,
# servicedesk@, postapro@dxpavel.cz, padre@seznam.cz, dxpavel@gmail.com,
# zamecnictvi.rozdalovice@gmail.com, dxpavel@icloud.com

CONTAINER_PREFIX=brogiasist
POSTGRES_PORT_HOST=5432
ATTACHMENTS_BIND=./attachments
```

---

## 5. KLÍČOVÉ DOKUMENTY (ČTI V TOMTO POŘADÍ na startu nové session)

> Tohle je **povinné čtení**, ne doporučení. Bez něj nemáš kontext.

| # | Soubor | Proč |
|---|---|---|
| 1 | `docs/SESSION-HANDOFF-D-CONTINUATION.md` | **PRIORITNÍ** — co bylo udělané, co zbývá, první krok |
| 2 | `docs/CONTEXT-NEW-CHAT.md` | aktuální stav projektu, co běží, co je TODO |
| 3 | `docs/brogiasist-semantics-v1.md` (sekce 21) | spec + implementační status na branch `2` |
| 4 | `docs/BUGS.md` | aktivní bugy (BUG-009 group disjoint, BUG-010 Mail.app headers) |
| 5 | `docs/brogiasist-lessons-learned-v1.md` (sekce 35–37) | důležité macOS gotchas: fork bug, TCC FDA, JXA |
| 6 | `docs/DOC-MAP.md` | mapa všech dokumentů — pokud něco není tam, neexistuje |

**Přečti je přes `Read` tool, ne z memory.**

---

## 6. STRUKTURA PROJEKTU (cesty)

```
/Users/pavel/SynologyDrive/001 DXP/009 BrogiASIST/   # root, sync s Synology + git
├── CLAUDE.md                                          # ← TADY JSI (autoritativní pravda)
├── .env                                               # credentials (NE V GITU)
├── .env.example                                       # template
├── docker-compose.yml                                 # společný DEV+PROD compose
├── deploy.sh                                          # PROD deploy script (na VM 103)
├── docs/                                              # všechny markdown docs (15 souborů)
│   ├── DOC-MAP.md                                     # mapa
│   ├── CONTEXT-NEW-CHAT.md                            # entry point
│   ├── SESSION-HANDOFF-D-CONTINUATION.md              # aktivní handoff
│   ├── brogiasist-{semantics,architecture,data-dictionary,
│   │              api-reference,infrastructure,credentials,
│   │              lessons-learned,workflows,feature-plan}-v1.md
│   ├── BUGS.md
│   └── _archive/                                      # neaktuální, ale ne smazané
├── services/
│   ├── apple-bridge/main.py                           # Apple Bridge FastAPI (PROD: Apple Studio)
│   ├── ingest/
│   │   ├── scheduler.py                               # APScheduler entry
│   │   ├── ingest_email.py + _idle.py                 # IMAP IDLE + scan
│   │   ├── ingest_apple_apps.py                       # OF + Notes + Reminders + Contacts + Calendar
│   │   ├── ingest_rss.py + _youtube.py + _mantis.py
│   │   ├── classify_emails.py                         # Llama + Claude verifikace + decision_engine
│   │   ├── decision_engine.py                         # ⭐ NEW v2 — rule engine
│   │   ├── pending_worker.py                          # ⭐ NEW v2 — queue pro Apple offline
│   │   ├── chroma_audit.py + chroma_dedup.py          # ⭐ NEW v2 — údržba Chromy
│   │   ├── notify_emails.py                           # TG notifikace klasifikovaných
│   │   ├── telegram_callback.py                       # TG callback handler
│   │   ├── imap_actions.py                            # mark_read, move_to_trash, move_to_brogi_folder
│   │   ├── chroma_client.py                           # ChromaDB klient
│   │   ├── backfill_*.py                              # retroaktivní akce
│   │   └── api.py                                     # scheduler internal HTTP API (port 9001)
│   └── dashboard/
│       ├── main.py                                    # FastAPI
│       └── templates/                                 # Jinja2 (base.html + index/admin/úkoly/...)
├── sql/                                               # 014 migrací, idempotentní
│   ├── 001_init.sql ... 011_claude_sender_verdicts.sql
│   ├── 012_apple_contacts_groups.sql                  # ⭐ NEW v2
│   ├── 013_decision_rules.sql                         # ⭐ NEW v2
│   └── 014_email_semantics_v1.sql                     # ⭐ NEW v2
├── tmp/                                               # backupy + temp scripts (NE v gitu)
└── .git/                                              # 2.4 MB
```

---

## 7. DEPLOY WORKFLOWS

### A) PROD VM 103 (scheduler / dashboard / DB)

```bash
# lokálně
git push origin 2

# na VM 103
ssh pavel@10.55.2.231
cd ~/brogiasist
git pull origin 2

# pokud nová SQL migrace
PGUSER=$(grep ^POSTGRES_USER .env | cut -d= -f2)
PGDB=$(grep ^POSTGRES_DB .env | cut -d= -f2)
docker exec -i brogiasist-postgres psql -U $PGUSER -d $PGDB < sql/NNN_*.sql

# rebuild dotčené služby
docker compose build scheduler && docker compose up -d scheduler
# nebo
docker compose build dashboard && docker compose up -d dashboard
```

### B) Apple Studio (Apple Bridge — `services/apple-bridge/main.py`)

```bash
# backup remote main.py
ssh dxpavel@10.55.2.117 "cp /Users/dxpavel/brogiasist-bridge/main.py main.py.backup-$(date +%Y%m%d)"

# scp aktualizace
scp services/apple-bridge/main.py dxpavel@10.55.2.117:/Users/dxpavel/brogiasist-bridge/main.py

# reload launchd (NE pkill, NE killall)
ssh dxpavel@10.55.2.117 "launchctl unload ~/Library/LaunchAgents/cz.brogiasist.apple-bridge.plist && sleep 2 && launchctl load ~/Library/LaunchAgents/cz.brogiasist.apple-bridge.plist"

# verify
ssh dxpavel@10.55.2.117 "curl -sm 5 http://localhost:9100/health"
```

### C) Lokální MacBook (DEV — pokud Pavel chce vyzkoušet)

```bash
# Apple Bridge lokální má taky launchd (běží jako 1416 nebo podobně)
launchctl unload ~/Library/LaunchAgents/cz.brogiasist.apple-bridge.plist
launchctl load   ~/Library/LaunchAgents/cz.brogiasist.apple-bridge.plist
# pkill je špatně — nezachová autostart
```

---

## 8. CO BĚŽÍ NA PROD (předpoklady — VŽDY OVĚŘ příkazem)

### Ověření jedním příkazem

```bash
ssh pavel@10.55.2.231 "cd ~/brogiasist && docker compose ps"
ssh dxpavel@10.55.2.117 "launchctl list | grep brogi && curl -sm 5 http://localhost:9100/health"
```

### Předpokládané intervals v scheduleru

| Job | Interval | Akce |
|---|---|---|
| job_email_scan | 30 min | IMAP scan (backup k IDLE) |
| job_rss | 30 min | The Old Reader RSS |
| job_mantis | 30 min | MantisBT issues |
| job_youtube | 2 h | YouTube |
| ingest_omnifocus | 10 min | OF tasks z Apple Bridge |
| ingest_notes | 30 min | Apple Notes |
| ingest_reminders | 15 min | Apple Reminders |
| **ingest_contacts** | **12 h** | Apple Contacts (hash check, viz sekce 9) |
| ingest_calendar | 15 min | Apple Calendar |
| classify_new_emails | 5 min | Llama klasifikace + decision_rules |
| notify_classified_emails | 2 min | TG notifikace |
| job_imap_login_check | 5 min | IMAP IDLE health |
| **drain_queue** | **1 min** | Pending actions queue worker (degraded mode) |

---

## 9. PAVLOVA ROZHODNUTÍ (závazná)

| Datum | Rozhodnutí | Důvod |
|---|---|---|
| 2026-04-22 | Stack: PG + ChromaDB v Dockeru, dataflow raw→DB→decide→execute | architektura |
| 2026-04-22 | Mirror table + action_log VŽDY (aktuálně Chroma email_actions) | žádná akce mimo log |
| 2026-04-25 | Action logging do **Chroma `email_actions`**, NE PG `actions` (placeholder) | Vector embedding pro pattern matching |
| 2026-04-26 | **PROD migrace na VM 103 + Apple Studio** (NE Forpsi VPS) | LAN, žádná veřejná IP |
| 2026-04-26 | **Email Semantics v1 spec** schválena (9 TYPů, 5 STATUS, 8 ACTION + 2undo, prefix `2` = „to") | Pavlovo rozhodnutí, doc autoritativní |
| 2026-04-26 | **Existující 25 emailů a 2360 kontaktů NEMIGRUJEME** — staré v starém formátu, nové v novém | Vývoj, nemá smysl rozkopávat historii |
| 2026-04-26 | Apple Contacts ingest **12 h** (ne 6 h) + hash check | Stačí 2× denně, 99% DB writes ušetřeno |
| 2026-04-26 | BUG-008 fix přes **`os.posix_spawn()`** (NE `OBJC_DISABLE_INITIALIZE_FORK_SAFETY` — na macOS 26.4 nefunguje) | macOS multi-threaded fork bug |
| 2026-04-27 | **Přidána ACTION `2del`** (univerzální „rychle smazat") — Trash + Chroma log, **NE**zapisuje `classification_rules` (sender se neoznačí jako spam). Tlačítko ve **všech** TYPech (var. C). 8 → 9 ACTIONs. | Pro duplicity / šum, kdy 2spam by zbytečně označil odesílatele jako spam pro budoucnost. Učení dál funguje přes Chroma `email_actions` (find_repeat_action). |

---

## 10. ZNÁMÉ BUGY (aktivní)

> Detaily v `docs/BUGS.md`. Tady jen pointer.

| ID | Severita | Co | Status |
|---|---|---|---|
| BUG-001 | medium | `_email_action` patří do sdíleného modulu, ne v telegram_callback.py | OPEN |
| BUG-004/005 | medium | iCloud IMAP IDLE flaky (`Unexpected IDLE response`, `socket EOF`) | OPEN — auto-recovery 30s funguje |
| BUG-006 | low | 12 emailů s `folder='BrogiASIST/*'` v DB pravděpodobně neexistuje na IMAPu | OPEN — datový dluh |
| BUG-008 | HIGH | Apple Bridge fork() crash | **FIXED 2026-04-26** (posix_spawn) |
| BUG-009 | HIGH | Group matching v decision_rules nematchne (data ve 2 disjoint datasets) | **FIXED 2026-04-27** (commit 6b43643) |
| BUG-010 | MEDIUM | Mail.app AppleScript neumí custom headers (X-Brogi-Auto) | OPEN — vyžaduje arch decision |
| BUG-011 | MEDIUM | JSONB `@>` case-sensitive v decision_engine | **FIXED 2026-04-27** (commit af5df96) |
| BUG-012 | MEDIUM | iCloud IMAP `data[0]=None` → `NoneType.split` crash | **FIXED 2026-05-04** |
| BUG-013 | MEDIUM | Llama vrací raw placeholder `<0.0-1.0>` v `confidence` → ValueError | **FIXED 2026-05-04** (commit b8e88a9) |
| BUG-014 | MEDIUM | `mark_read` po `move_to_trash` → `STORE illegal in state AUTH` | **FIXED 2026-05-04** (commit e5df8a7) |

---

## 11. COMMIT STYLE

```
<type>(<scope>): <krátký popis česky>

<podrobný popis: proč to děláš, co se změnilo, jaké jsou důsledky>

<volitelně bullets s detaily>

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

Type: `feat`, `fix`, `chore`, `docs`, `perf`, `refactor`, `test`.
Scope: typicky modul (`scheduler`, `apple-bridge`, `dashboard`, `ingest`, `D5`, atd.).

**Nepoužívej `--no-verify`** ani jiné způsoby obejití hooks.
**Nedělej amend na pushnutý commit** (vytvoř nový commit).
**Nepushuj force** bez explicitního pokynu.

---

## 12. COMMON GOTCHAS (čti pozorně)

### macOS fork() bug
- Apple Bridge na PROD MUSÍ používat `os.posix_spawn()` v `run_jxa`/`run_applescript`
- NE `subprocess.run()` (= multi-threaded fork crash)
- NE `OBJC_DISABLE_INITIALIZE_FORK_SAFETY=YES` (na 26.4 nefunguje)
- Detail: lessons sekce 35

### TCC FDA pro launchd-spawned procesy
- Bridge přes launchd **nedědí FDA** z user FDA seznamu
- Direct sqlite read na `~/Library/Application Support/AddressBook/` selže s PermissionError
- **Pivot:** použít JXA AppleEvents (Application('Contacts').people()) — separátní permission
- Detail: lessons sekce 36

### JXA performance
- JXA per-property volání je drahé (~50/s)
- Pro 1000+ záznamů: vzít vlastnosti per-collection (1× call), JOIN přes index v JS
- `properties()` batch + `try/catch` per záznam
- Detail: lessons sekce 37

### `Auto-Submitted: auto-generated` ≠ bounce (decision_rules trap)
- **Mají ho VŠECHNY** systémové notifikace (MantisBT issue updates, GitHub alerty, monitoring, cron jobs)
- **Skutečný bounce/DSN** se pozná podle `Content-Type: multipart/report` (RFC 3464)
- Pravidlo `header_bounce` v decision_rules → matchuje `Content-Type contains "multipart/report"`, NE `Auto-Submitted` (oprava 2026-04-27, MantisBT HOSPODARY ticket falešně dostal TYP=ERROR)
- Detail: incident `e55ecb66-...` v `email_messages`, fix v sql/013 + DB update

### Python long-running proces — `docker cp` ≠ reload
- Změny `.py` souborů v běžícím kontejneru bez restartu = **no-op** (kód je v paměti od importu při startu)
- Vždy `docker compose up -d --build <service>`, ne jen `docker cp` + `restart`
- Diag: `docker inspect ... --format '{{.State.StartedAt}}'` vs `git log --since="<StartedAt>"` na klíčové moduly
- Lessons sekce **40** + **41** (incident 2026-05-04: drift TG tlačítek)

### TG bot 409 Conflict = paralelní instance
- `getUpdates: 409 Conflict` = dvě instance pollují stejný `TELEGRAM_BOT_TOKEN`
- Callbacky se náhodně rozdělí mezi instance → nepředvídatelné UI (např. starý layout tlačítek z DEV)
- Před spuštěním DEV scheduleru ověř `docker ps | grep brogi-scheduler` že PROD je dolu (nebo opačně), případně použij separátní bot token

### IMAP SEARCH guard `(data[0] or b"")`
- iCloud IMAP občas vrací `data=[None]` při dočasných glitchích → `None.split()` → AttributeError
- Vždy `uids = (data[0] or b"").split() if data else []` (ne přímý `data[0].split()`)
- Backfill skripty mají guard `if typ == "OK" and data[0]` (OK), ostatní volání ošetřit
- Lessons sekce **44**, BUG-012

### IMAP transient errors (neblokující)
- `[Errno -3] Try again` (DNS z kontejneru)
- `EOF in violation of protocol`
- `socket error: EOF`
- Auto-reconnect 30s funguje. Ne paniku.

### Docker container names
- DEV: `brogi_postgres`, `brogi_scheduler` (CONTAINER_PREFIX=brogi)
- PROD: `brogiasist-postgres`, `brogiasist-scheduler` (CONTAINER_PREFIX=brogiasist)
- ⚠️ Neplést!

### Chroma access
- Z scheduler containeru: `httpx.get http://chromadb:8000/api/v2/...`
- Bez Python `chromadb` package (není v requirements) — používat HTTP API přímo
- Collection `email_actions` ID viz audit script

### Branch `2` vs `main`
- Aktuálně `2` má víc commitů než `main` (release v2 in progress)
- PROD běží z `2` (po `git pull origin 2`)
- Po dokončení H1+H2+H3 (viz handoff) → merge `2` → main + tag `v2.0`

---

## 13. KDYŽ SI NEJSI JISTÝ — DEFAULT BEHAVIOR

| Situace | Default |
|---|---|
| Není jasné, jaký branch / commit / stav | Spusť `git status` + `git log -1 --oneline` + ukáž Pavlovi, zeptej se |
| Není jasné, zda Pavel souhlasí s implementací | Zeptej se. Žádný autonomní zápis. |
| Memory tvrdí X, dokumentace tvrdí Y | **Dokumentace vyhrává.** Updatuj memory. |
| Není jasné, zda kód funguje | Spusť ho (test, smoke), neříkej „funguje" bez ověření |
| Pavel řekne „STOP" / „pauza" / je naštvaný | Okamžitě zastav, vrať se k poslední verifikované akci, zeptej se co chce |
| Změna by mohla zlomit PROD | Default je test lokálně → schvalování → deploy. Ne přímý PROD push. |
| Ne víš zda něco existuje (např. MCP server) | **`ToolSearch`** + `Read` + `Bash`. Neříkej „nemám přístup" bez ověření. |
| Pavel se ptá obecně („co dělá X?") | Krátká odpověď + pointer na konkrétní soubor/sekci dokumentace |

---

## 14. TYP/STATUS/ACTION semantika (sumár)

> Detail: `docs/brogiasist-semantics-v1.md`. Tady stručně.

**TYP** (klasifikace obsahu, velkými písmeny):
ÚKOL · DOKLAD · NABÍDKA · NOTIFIKACE · POZVÁNKA · INFO · ERROR · LIST · ENCRYPTED

**STATUS** (životní cyklus):
NOVÝ · PŘEČTENÝ · ČEKAJÍCÍ · ZPRACOVANÝ · SMAZANÝ

**`email_messages.task_status`** (sub-stav po klasifikaci, 2026-05-04 revize):
- `ČEKÁ-NA-ODPOVĚĎ` — Pavel poslal dotaz, čeká na třetí stranu
- `HOTOVO` · `→OF` · `→REM` · `→CAL` — výsledek user akce
- `NULL` — výchozí (vč. INFO/NOTIFIKACE bez follow-upu)
- ⚠️ `ČEKÁ-NA-MĚ` se **NIKDY** nezapisuje (redundantní s TYP=ÚKOL). Validace v `classify_emails.py` to filtruje.

**ACTION** (9 hodnot, malými, prefix `2` = „to"):
2of · 2rem · 2cal · 2note · 2hotovo · **2del** · 2spam · 2unsub · 2skip + 2undo (TTL 1h)

> **2del vs 2spam** (přidáno 2026-04-27):
> - `2del` = jednorázové smazání (Trash + Chroma log). Sender se NEoznačí jako spam.
> - `2spam` = smazání + zápis do `classification_rules` → další maily od sendera jdou auto-spam.
> Použij `2del` pro duplicity / šum, `2spam` pro skutečné spammery.

**Decision flow:**
header check → skupina BLOCKED ignoruj → VIP / personal flagy → Chroma vzor → Llama AI

---

## 15. KONTAKTY / OWNER

- Owner: **Pavel** (dxpavel@me.com / dxpavel@gmail.com / pavel@dxpsolutions.cz / brogi@dxpsolutions.cz)
- GitHub: `dxpavel/BrogiASIST`
- Synology Drive: `/Users/pavel/SynologyDrive/001 DXP/009 BrogiASIST/` (sync s NAS)

---

## 16. CHANGELOG TOHOTO SOUBORU

| Datum | Verze | Změna |
|---|---|---|
| 2026-04-26 | 1.0 | Vytvořeno — autoritativní pravda po release v2 work day |
| 2026-04-27 | 1.1 | Přidána ACTION `2del` (var. C — ve všech TYPech). Update sekce 9 (rozhodnutí), sekce 14 (sumár) — 8 → 9 ACTIONs. |
| 2026-05-04 | 1.2 | Sekce 12 — přidány dva nové gotchas: Python long-running + `docker cp`, TG bot 409 Conflict (paralelní instance). Pointery na lessons #40, #41. |
| 2026-05-04 | 1.3 | Sekce 14 — `task_status` sub-stav doplněn, `ČEKÁ-NA-MĚ` odstraněno (redundantní s TYP=ÚKOL). Lessons #42 (placeholder strings sanitize) + #43 (univerzální 3×3 layout always-show). |
| 2026-05-04 | 1.4 | Sekce 12 — IMAP `data[0] or b""` guard (BUG-012 fix). Sekce 10 — BUG-009/011 marked FIXED, BUG-012 added. Lessons sekce **44**. |
| 2026-05-04 | 1.5 | Sekce 10 — BUG-013/014 marked FIXED+DEPLOYED. M2/M3/M4/M5-pre deployed na PROD (commit 084992b). Lessons sekce **45–48**. M5 spec viz `docs/feature-specs/FEATURE-AI-CASCADE-v1.md`. |

> **Edituj tento soubor kdykoli se změní realita** (PROD migrace, nové branch konvence,
> nové bugy, přejmenování, nové infrastructure...). Commit + push, příští session
> Claude bude vědět.

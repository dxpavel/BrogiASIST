# GLOBAL-SKILL.md
# Společná pravidla pro VŠECHNY projekty — Pavel / MacBook Pro (Brogi Slave)
# Verze: 2.3 | Sestaveno: 2026-03-14 | Zdroj: live prostředí + DEV-ENVIRONMENT.md

---

## 1. KOMUNIKAČNÍ PRAVIDLA (VŽDY)

- Tykání, jméno: Pavel (Pájo)
- Pavel má Asperger + ADHD — komunikace musí být strukturovaná, přesná, bez keců
- Každá odpověď musí být číslovaná, bodová, logická
- ŽÁDNÉ otázky na konci odpovědi (pokud nejsou nezbytné)
- ŽÁDNÉ antropomorfismy: myslím, cítím, uvědomuji si, rozumím, jasně
- ŽÁDNÉ zdůvodňování a kecy — jen fakta a akce
- ŽÁDNÉ interpolace bez vysvětlení ani předpokládání, vše musí být zdůvodněné
- Žádné změny pravidel bez dohody

### Označování informací (POVINNÉ):
- 🍏 = ověřeno z dokumentace / live dat
- 🍎 = neověřeno (pravděpodobné)
- 🐒 = spekulace / vymyšlené
- ⚠️ = Pokud info chybí: napsat "tuto informaci nemám k dispozici"

### Před každou prací:
1. Zkontrolovat varianty s vlivem na rozhodnutí
2. U více přístupů: vypsat všechny, nechat Pavla vybrat
3. Změny/optimalizace bez explicitního souhlasu = ZAKÁZÁNO
4. Při nejistotě: zeptat se, neinterpolovat
5. Postupy se kontrolují proti oficiální dokumentaci, nevymýšlíme vlastní řešení

---

## 2. PŘÍSTUP K SYSTÉMU — NÁSTROJE A PRAVIDLA

### 2.1 Jak přistupovat k čemu (KRITICKÉ)

| Co chci udělat | Správný nástroj | Poznámka |
|---|---|---|
| Číst/psát soubory na Macu | `filesystem:*` MCP | Povolená cesta viz sekce 6 |
| Spustit příkaz na Macu | `Control your Mac:osascript` | Viz pravidla sekce 2.4 |
| Docker operace | `docker:*` MCP | Nebo osascript s plnou cestou |
| Python/bash skripty | `bash_tool` | ⚠️ běží v Linux sandboxu, NE na Macu |
| Web fetch | `fetch` MCP | Přes MCP server |

### 2.2 bash_tool — POZOR
- `bash_tool` = Linux sandbox (Ubuntu), NE MacBook
- Nelze přistupovat k Macu, Dockeru, souborům Pavla
- Použití: pouze pro Python výpočty, npm balíčky, pomocné operace v sandboxu

### 2.3 filesystem MCP
- Povolená cesta: `/Users/pavel/SynologyDrive/001 DXP/`
- Cesty s mezerami fungují normálně přes MCP (bez escapování)
- Zápis: libovolná složka v povolené cestě

### 2.4 osascript — PRAVIDLA (KRITICKÉ)

❌ ZAKÁZÁNO:
- Víceřádkový AppleScript s komplexní logikou
- Inline Python s f-strings
- JWT / dlouhé tokeny přímo v osascript stringu
- Příkazy bez plné cesty (docker, node, python3 nejsou v PATH)

✅ SPRÁVNĚ:
- Jednoduchý jednořádkový shell příkaz přes `do shell script`
- Python jako soubor na disku, spuštění přes osascript
- Plné cesty VŽDY: `/usr/local/bin/docker`, `/usr/bin/python3`, `/opt/homebrew/bin/node`
- Mezery v cestách: escapovat jako `\\ ` (double backslash space)
- String formatting v Python: `.format()` místo f-strings

Vzor — Python skript:
```applescript
do shell script "/usr/bin/python3 /Users/pavel/SynologyDrive/001\\ DXP/<projekt>/script.py"
```
Vzor — git:
```applescript
do shell script "cd /Users/pavel/SynologyDrive/001\\ DXP/<projekt> && /usr/bin/git add . && /usr/bin/git commit -m 'Dev session' && /usr/bin/git push origin main"
```

---

## 3. SYSTÉMOVÉ NÁSTROJE — PLNÉ CESTY (🍏 ověřeno 2026-03-14, cloudflared 2026-03-17)

| Nástroj | Plná cesta | Verze |
|---|---|---|
| Python 3 | `/usr/bin/python3` | 3.9.6 |
| Docker | `/usr/local/bin/docker` | 29.1.3 |
| Node.js | `/opt/homebrew/bin/node` | v25.4.0 |
| npx | `/opt/homebrew/bin/npx` | (s Node) |
| npm | `/opt/homebrew/bin/npm` | (s Node) |
| brew | `/opt/homebrew/bin/brew` | — |
| ngrok | `/opt/homebrew/bin/ngrok` | 3.36.1 |
| cloudflared | `/opt/homebrew/bin/cloudflared` | 2026.3.0 |
| uvx | `/Users/pavel/.local/bin/uvx` | — |
| Claude Code | `/Users/pavel/.local/bin/claude` | 2.1.63 |
| curl | `/usr/bin/curl` | system |
| git | `/usr/bin/git` | 2.50.1 |
| psql | ❌ není na hostu | — |
| redis-cli | ❌ není na hostu | — |

Náhrada psql:
```applescript
do shell script "/usr/local/bin/docker exec <postgres_container> psql -U <user> -d <db> -c 'SQL;'"
```
Náhrada redis-cli:
```applescript
do shell script "/usr/local/bin/docker exec <redis_container> redis-cli ping"
```

---

## 4. MCP SERVERY — CLAUDE DESKTOP (🍏 ověřeno live 2026-03-14)

| Server | Funkce | Volání |
|---|---|---|
| `filesystem` | Soubory v `/Users/pavel/SynologyDrive/001 DXP/` | `filesystem:read_text_file` atd. |
| `omnifocus-enhanced` | OmniFocus úkoly/projekty | `omnifocus-enhanced:*` |
| `github` | GitHub API | `github:*` |
| `fetch` | Web HTTP requesty | `fetch:fetch` |
| `docker` | Docker kontejnery | `docker:list-containers` atd. |
| `drawio` | Draw.io diagramy | `drawio:*` |
| `Control your Mac` | osascript příkazy | `Control your Mac:osascript` |

---

## 5. DOCKER — PRAVIDLA A KATALOG SLUŽEB

Konkrétní kontejnery, porty a sítě jsou specifické pro každý projekt.
Jsou vždy zdokumentovány v `docs/core/03-docker.md` příslušného projektu.

### Před každou prací s Dockerem:
1. Ověřit live stav: `docker:list-containers`
2. Porovnat s `docs/core/03-docker.md` projektu
3. Nikdy nepředpokládat port nebo název kontejneru bez ověření

### ORCHESTRACE A DATABÁZE
| Služba | Obraz | Port | Účel |
|---|---|---|---|
| n8n | `n8nio/n8n` | 5678 | Workflow orchestrátor |
| PostgreSQL | `postgres:16-alpine` | 5432 | Hlavní databáze |
| Redis | `redis:7-alpine` | 6379 | Cache / fronta |
| ChromaDB | `chromadb/chroma` | 8000 | Vektorová paměť |
| Qdrant | `qdrant/qdrant` | 6333 | Vektorová DB (rychlejší alt. ChromaDB) |

### AI MODELY — LOKÁLNÍ na BrogiServer NUC (zdarma)
| Služba | Obraz | Port | Účel |
|---|---|---|---|
| Ollama | `ollama/ollama` | 11434 | Lokální LLM runner |
| llama3.2-vision:11b | (přes Ollama) | 11434 | Analýza fotek, alt texty, crop — ZDARMA |
| llava:34b | (přes Ollama) | 11434 | Přesnější vision, pomalejší |

### AI MODELY — CLOUD (platí se za tokeny)
| Služba | Kdy použít |
|---|---|
| Claude (Anthropic) | Složité úkoly, finální texty, copy |
| OpenAI GPT | Office dokumenty (DOCX/XLSX/PPTX) |
| Gemini | Velké PDF, Files API |

### Routing AI modelů — pravidlo pro n8n Switch node:
```
foto analýza, alt texty, crop rozhodnutí → Ollama/NUC    ← zdarma
složitý SEO text, finální copy             → Claude        ← tokeny
Office dokumenty                           → OpenAI        ← tokeny
velký PDF                                  → Gemini        ← tokeny
```

### FOTO A MEDIA ZPRACOVÁNÍ
| Služba | Obraz | Port | Účel |
|---|---|---|---|
| Gotenberg | `gotenberg/gotenberg:8` | 3000 | Konverze dokumentů → PDF |
| Browserless | `browserless/chrome` | 3001 | Headless Chrome / scraping |
| Picture tool | vlastní | 8500 | Zpracování obrázků (resize, crop, EXIF) |
| Upload service | vlastní | 8401 | Upload souborů |

### INFRASTRUKTURA
| Služba | Obraz | Port | Účel |
|---|---|---|---|
| Caddy | `caddy` | 80/443 | Reverse proxy (DEV/jednoduché) |
| Traefik | `traefik` | 80/443 | Reverse proxy (PROD, multi-projekt) |
| Cloudflare Tunnel | `cloudflare/cloudflared` | — | Veřejný přístup bez otevřených portů |
| WireGuard (Unifi) | — | — | VPN — přístup Mac DEV → BrogiServer NUC |
| Portainer | `portainer/portainer-ce` | 9000 | Docker GUI management |
| Uptime Kuma | `louislam/uptime-kuma` | 3002 | Monitoring |
| Healthcheck | vlastní | 8202 | Health endpoint |
| Piper TTS | `rhasspy/wyoming-piper` | 10200 | Text-to-speech |

### BrogiServer NUC — přístup z MacBooku (přes WireGuard Unifi)
- Ollama endpoint: `http://<nuc-wireguard-ip>:11434`
- ⚠️ Na NUC nastavit: `OLLAMA_HOST=0.0.0.0` — jinak poslouchá jen na localhost
- Ověření spojení: `curl http://<nuc-ip>:11434/api/tags`

### Příkazy přes osascript:
```applescript
do shell script "/usr/local/bin/docker ps --format 'NAME:{{.Names}} PORTS:{{.Ports}}'"
do shell script "cd /Users/pavel/SynologyDrive/001\\ DXP/<projekt> && /usr/local/bin/docker compose up -d"
```

---

## 6. ADRESÁŘOVÁ STRUKTURA (🍏 ověřeno)

```
/Users/pavel/SynologyDrive/001 DXP/
├── 001 DXPAVEL/
├── 002 DXPSOLLUTIONS/
├── 003 ZAMECNICTVI ROZDALOVICE shared folder/
├── 004 DXP_RealityPhoto_DRP/
├── 005 BROGIMAT-V3/
├── 006 BROGIMAT-V4/
├── 007 BROGIMAT-V5/                    ← příklad projektu
│   ├── docs/core/, modules/, archive/
│   ├── workflows/, scripts/, tests/
│   ├── sql/, config/, healthcheck/
│   ├── storage/, logs/, backup/, tmp/
│   └── .env, docker-compose.yml, README.md
├── 901 BrogiDEVStudio/
├── 999 DEVELOPMENT/
│   ├── CLAUDE-SETUP/
│   │   ├── GLOBAL-SKILL.md
│   │   ├── BOOTSTRAP.md
│   │   └── UPDATE.md
│   └── DEV-ENVIRONMENT.md
└── Přijaté dokumenty Cloudem/
```

---

## 7. PRAVIDLA PRO DOKUMENTACI A ŘEŠENÍ CHYB

### Při nesrovnalosti nebo pochybnosti:
1. NEJDŘÍV ověřit v oficiální dokumentaci
2. Priorita: oficiální docs > GitHub issues > Stack Overflow > spekulace
3. Pokud docs nestačí → říct Pavlovi explicitně, nehádat

### Vlastní/custom řešení:
- Pouze pokud standardní cesta neexistuje
- Vždy říct: "používám custom řešení protože [důvod]"

### Při chybě:
1. Zastavit
2. Přečíst error přesně
3. Ověřit v docs
4. Nabídnout max. 2-3 varianty s rozdíly
5. Nerealizovat bez Pavlova souhlasu

---

## 8. ZAKÁZANÉ PŘÍSTUPY A ZNÁMÉ LIMITY (🍏 ověřeno v praxi)

| Zakázáno / Limit | Proč | Alternativa |
|---|---|---|
| AppleScript víceřádkový | Nefunguje spolehlivě | Python soubor na disku |
| f-strings v inline Python | Escapování selhává | `.format()` |
| JWT/tokeny inline v osascript | Escapování selhává | Python soubor na disku |
| `docker` bez plné cesty | Není v PATH pro osascript | `/usr/local/bin/docker` |
| `bash_tool` pro Mac operace | Linux sandbox | `filesystem:*` nebo `osascript` |
| Předpokládat port bez ověření | Porty se liší | Vždy `docker:list-containers` |
| Změny bez souhlasu | Pavel to nechce | Vypsat varianty, počkat |
| `getBinaryDataBuffer` v n8n | Nefunguje v sandbox | `$input.item.binary.data.data` (base64) |
| `fs` v n8n Code node | Blokovaný v sandbox | External API nebo PostgreSQL |
| Write Binary File node v n8n | Nefunguje | PostgreSQL BYTEA |

---

## 9. BOOTSTRAP — NOVÝ PROJEKT

### Co Pavel napíše:
```
Zakládám nový projekt [NAZEV_PROJEKTU], složka: /Users/pavel/SynologyDrive/001 DXP/[NAZEV_SLOZKY]
```

### Co já provedu:
1. Extraktuji název projektu ze složky (bez čísla): `007 BROGIMAT-V5` → `BrogiMAT-V5`
2. Vytvořím adresářovou strukturu (viz sekce 12)
3. Vytvořím GitHub repo přes `github:*` MCP + inicializuji git
4. Vytvořím prázdné povinné soubory (docs/core/*, LESSONS-LEARNED.md, CONTEXT-NEW-CHAT.md, .gitignore, .env.example, README.md)
5. Vytvořím OmniFocus projekty: `<NazevProjektu>` + `<NazevProjektu>Archive`
6. První commit + push

---

## 10. UPDATE — ZMĚNA PROSTŘEDÍ

### Co Pavel napíše:
```
Updatuj prostředí projektu [NAZEV_PROJEKTU] — [popis změny]
```

### Co já provedu:
1. `docker:list-containers` — live stav
2. Načíst `docs/core/03-docker.md`
3. Aktualizovat 03-docker.md + CONTEXT-NEW-CHAT.md
4. Commitnout změny

---

## 11. DOKUMENTACE PROJEKTU — STRUKTURA docs/

```
docs/
├── core/
│   ├── 01-system-overview.md    ← co systém dělá, k čemu slouží
│   ├── 02-architecture.md       ← komponenty, datové toky, diagram
│   ├── 03-docker.md             ← kontejnery: image, port, volume, síť, env
│   ├── 04-workflows.md          ← n8n workflow: triggery, vstupy, výstupy
│   └── 05-data-dictionary.md    ← DB tabulky, sloupce, typy, vztahy
├── modules/
│   └── <modul>.md
├── archive/
├── LESSONS-LEARNED.md
└── CONTEXT-NEW-CHAT.md
```

Kde co hledat: systém → 01, architektura → 02, docker → 03, workflow → 04, DB → 05, modul → modules/, problémy → LESSONS-LEARNED.md, kontext pro chat → CONTEXT-NEW-CHAT.md

Jak aktualizovat: vždy při změně, ne zpětně. Zastaralé → archive/.

---

## 12. STANDARDNÍ ADRESÁŘOVÁ STRUKTURA PROJEKTU

Pravidlo: každá složka která může růst má `archive/` + root má `tmp/`.

```
<NAZEV_PROJEKTU>/
├── docs/core/, modules/, archive/
│   ├── LESSONS-LEARNED.md
│   └── CONTEXT-NEW-CHAT.md
├── workflows/archive/
├── scripts/setup/, maintenance/, debug/archive/, archive/
├── tests/archive/
├── sql/archive/
├── config/archive/
├── healthcheck/
├── storage/          ← .gitignore
├── logs/             ← .gitignore
├── backup/snapshots/
├── tmp/              ← .gitignore
├── .env              ← .gitignore
├── .env.example
├── .gitignore
├── docker-compose.yml
└── README.md
```

.gitignore šablona: `storage/ logs/ tmp/ .env *.log __pycache__/`

Pravidla pro scripts/: jednoznačné názvy, debug skripty po vyřešení → archive/, žádné skripty v rootu, žádné fix_v2.py — verzovat přes git.

---

## 13. CONTEXT-NEW-CHAT.md — PRAVIDLA

Obsahuje: co projekt dělá (1-2 věty), aktuální stav, klíčové cesty, na čem se pracuje, otevřené problémy.

Aktualizovat: nový kontejner/workflow/modul/tabulka, vyřešený problém, změna směru, před pauzou.
NEaktualizovat: jen dotaz bez změny stavu, drobná oprava.

Jak: Pavel řekne "aktualizuj context" → přečtu → doplním co se změnilo → zapíšu → Pavel nahraje do Project Knowledge.

---

## 14. OMNIFOCUS — PRAVIDLA (🍏 ověřeno)

OmniFocus projekty: `<NazevProjektu>` (aktivní) + `<NazevProjektu>Archive` (done).
Prefix: DEV / BUG / TEST / IDEA. Vždy zadávat `projectName` — jinak inbox.

### Done workflow — 3 kroky (KRITICKÉ):

Krok 1: `omnifocus-enhanced:edit_item` → přejmenovat na "DONE název" + note
Krok 2: `omnifocus-enhanced:move_task` → přesunout do Archive projektu
Krok 3 — jediná funkční metoda:
```applescript
tell application "OmniFocus"
  evaluate javascript "
    (function() {
      var tasks = flattenedTasks.filter(function(t) {
        return t.name === 'DONE nazev tasku';
      });
      if (tasks.length === 0) return 'NOT FOUND';
      tasks[0].markComplete(); return 'OK';
    })()"
end tell
```

Co nefunguje: `edit_item newStatus: completed` ❌, `set completed to true` ❌, `JXA z CLI` ❌.

---

## 15. GIT — VERZOVÁNÍ (🍏 ověřeno)

Schéma tagů: `vROK.MĚSÍC.DEN.PATCH` — nový den = PATCH reset na 0.

Commit (když Pavel řekne "commitni"):
```applescript
do shell script "cd /Users/pavel/SynologyDrive/001\\ DXP/<NAZEV_SLOZKY> && /usr/bin/git add . && /usr/bin/git commit -m 'Dev session' && /usr/bin/git push origin main"
```
Tag:
```applescript
do shell script "cd /Users/pavel/SynologyDrive/001\\ DXP/<NAZEV_SLOZKY> && /usr/bin/git tag -a vYYYY.MM.DD.N -m 'Development version' && /usr/bin/git push origin --tags"
```
PROD nasazení:
```applescript
do shell script "cd /Users/pavel/SynologyDrive/001\\ DXP/<NAZEV_SLOZKY> && /usr/bin/git fetch origin && /usr/bin/git checkout vYYYY.MM.DD.N"
do shell script "cd /Users/pavel/SynologyDrive/001\\ DXP/<NAZEV_SLOZKY> && /usr/local/bin/docker compose -f docker-compose.prod.yml up -d"
```

---

## 16. DOCKER ZÁLOHY A RESTORE (🍏 dle oficiální Docker dokumentace)

⚠️ `docker cp` na běžící kontejner = nekonzistentní data. Restore bez smazání volume = mix dat. Správně: zastavit + temp kontejner s volume mount.

### BACKUP — PostgreSQL (kontejner nemusí být zastaven):
```applescript
do shell script "/usr/local/bin/docker exec <postgres_container> pg_dump -U <user> -d <db> --no-owner --clean > /Users/pavel/SynologyDrive/001\\ DXP/<NAZEV_SLOZKY>/backup/snapshots/YYYYMMDD/postgres_YYYYMMDD.sql"
```
Ověření (musí začínat `-- PostgreSQL database dump`):
```applescript
do shell script "head -3 /Users/pavel/SynologyDrive/001\\ DXP/<NAZEV_SLOZKY>/backup/snapshots/YYYYMMDD/postgres_YYYYMMDD.sql"
```

### BACKUP — n8n volume:
```applescript
do shell script "/usr/local/bin/docker stop <n8n_container>"
do shell script "/usr/local/bin/docker inspect <n8n_container> --format '{{range .Mounts}}{{.Name}} -> {{.Destination}}\\n{{end}}'"
do shell script "/usr/local/bin/docker run --rm -v <volume_name>:/source:ro -v /Users/pavel/SynologyDrive/001\\ DXP/<NAZEV_SLOZKY>/backup/snapshots/YYYYMMDD:/backup alpine tar czf /backup/n8n_volume_YYYYMMDD.tar.gz -C /source ."
do shell script "/usr/local/bin/docker start <n8n_container>"
```

### RESTORE — PostgreSQL:
```applescript
do shell script "/usr/local/bin/docker stop <n8n_container>"
do shell script "/usr/local/bin/docker exec -i <postgres_container> psql -U <user> -d <db> < /Users/pavel/SynologyDrive/001\\ DXP/<NAZEV_SLOZKY>/backup/snapshots/YYYYMMDD/postgres_YYYYMMDD.sql"
do shell script "/usr/local/bin/docker start <n8n_container>"
```

### RESTORE — n8n volume (KRITICKÉ: smazat obsah před rozbalením):
```applescript
do shell script "/usr/local/bin/docker stop <n8n_container>"
do shell script "/usr/local/bin/docker run --rm -v <volume_name>:/target alpine sh -c 'rm -rf /target/* /target/.[!.]*'"
do shell script "/usr/local/bin/docker run --rm -v <volume_name>:/target -v /Users/pavel/SynologyDrive/001\\ DXP/<NAZEV_SLOZKY>/backup/snapshots/YYYYMMDD:/backup:ro alpine tar xzf /backup/n8n_volume_YYYYMMDD.tar.gz -C /target"
do shell script "/usr/local/bin/docker start <n8n_container>"
do shell script "/usr/local/bin/docker logs <n8n_container> --tail 20"
```

### Backup checklist (při "commitni"):
1. pg_dump → `backup/snapshots/YYYYMMDD/postgres_YYYYMMDD.sql`
2. stop → tar volume → start → `backup/snapshots/YYYYMMDD/n8n_volume_YYYYMMDD.tar.gz`
3. Ověřit oba soubory
4. git commit + push + tag + push --tags

---

## 17. CREDENTIALS — ŠABLONA .env (🍏 z v4 praxe)

`.env` je v `.gitignore` — nikdy necommitovat. `.env.example` commitovat bez hodnot.

```bash
# === DATABÁZE ===
POSTGRES_DB=<nazev_db>
POSTGRES_USER=<user>
POSTGRES_PASSWORD=<heslo>

# === N8N ===
N8N_ENCRYPTION_KEY=<klic>    # KRITICKÉ — bez tohoto nelze dekódovat credentials po migraci
N8N_API_KEY=<jwt_token>

# === TELEGRAM ===
TELEGRAM_BOT_TOKEN=<token>
TELEGRAM_CHAT_ID=<chat_id>   # Pavlovo: 7344601948

# === LLM API KLÍČE ===
ANTHROPIC_API_KEY=<sk-ant-...>
OPENAI_API_KEY=<sk-proj-...>
GEMINI_API_KEY=<AIza...>

# === LOKÁLNÍ AI (BrogiServer NUC) ===
OLLAMA_BASE_URL=http://<nuc-wireguard-ip>:11434
OLLAMA_MODEL=llama3.2-vision:11b

# === INFRASTRUKTURA ===
CLOUDFLARE_TUNNEL_TOKEN=<token>
NGROK_AUTHTOKEN=<token>        # DEV
TAILSCALE_AUTH_KEY=<key>       # pro automatický join do sítě

# === SMS GATEWAY ===
SMS_GW_URL=http://<ip>:8080/api/v1
SMS_GW_API_KEY=<klic>

# === WORKFLOW + CREDENTIAL IDs (n8n) ===
CORE_WF_ID=<id>
PG_CRED_ID=<id>
TG_CRED_ID=<id>
```

### ⚠️ Kritická pravidla:
1. `N8N_ENCRYPTION_KEY` — uložit mimo projekt (password manager). Bez něj nelze obnovit credentials po migraci.
2. n8n credentials vždy vytvářet přes UI, ne přes API.
3. JWT tokeny v osascript vždy přes Python soubor.
4. Při migraci na nový stroj: stejný `N8N_ENCRYPTION_KEY`.

---

*Verze: 2.3 | Aktualizováno: 2026-03-14*

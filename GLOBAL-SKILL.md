---
Název: GLOBAL-SKILL
Soubor: GLOBAL-SKILL.md
Verze: 1.0
Poslední aktualizace: 2026-03-26
Popis: Pravidla projektu BrogiMatAssistance — nástroje, limity, konvence
Změněno v: vytvořen (bootstrap projektu z šablony 999 DEVELOPMENT)
---

# GLOBAL-SKILL.md
# Pravidla pro projekt BrogiMatAssistance — Pavel / MacBook Pro (Brogi Slave)
# Verze: 1.0 | Sestaveno: 2026-03-26 | Zdroj: 999 DEVELOPMENT/CLAUDE-SETUP/GLOBAL-SKILL.md v2.3

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
do shell script "/usr/bin/python3 /Users/pavel/SynologyDrive/001\\ DXP/009\\ BrogiMAT\\ Assistance/script.py"
```
Vzor — git:
```applescript
do shell script "cd /Users/pavel/SynologyDrive/001\\ DXP/009\\ BrogiMAT\\ Assistance && /usr/bin/git add . && /usr/bin/git commit -m 'Dev session' && /usr/bin/git push origin main"
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
do shell script "/usr/local/bin/docker exec assistance-postgres psql -U <user> -d assistance -c 'SQL;'"
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

## 5. DOCKER — BrogiMatAssistance

Kontejnery specifické pro tento projekt:

| Služba | Obraz | Port | Účel |
|---|---|---|---|
| assistance-postgres | `postgres:16-alpine` | TBD | Logy, analytika, statistiky, poloha |
| assistance-chroma | `chromadb/chroma` | TBD | Pavel DNA, vzorce chování, profil |

Detaily viz `docs/brogimat-assistance-infrastructure-v1.md`

### Před každou prací s Dockerem:
1. Ověřit live stav: `docker:list-containers`
2. Porovnat s dokumentací
3. Nikdy nepředpokládat port nebo název kontejneru bez ověření

---

## 6. ADRESÁŘOVÁ STRUKTURA (🍏 ověřeno)

```
/Users/pavel/SynologyDrive/001 DXP/009 BrogiMAT Assistance/
├── docs/
│   ├── modules/
│   ├── DOC-MAP.md
│   ├── CONTEXT-NEW-CHAT.md
│   └── LESSONS-LEARNED.md
├── archive/
├── workflows/
├── scripts/setup/, maintenance/, debug/
├── tests/
├── sql/
├── config/
├── healthcheck/
├── storage/          ← .gitignore
├── logs/             ← .gitignore
├── backup/snapshots/
├── tmp/              ← .gitignore
├── CLAUDE-SETUP/     ← root šablony (read-only reference)
├── GLOBAL-SKILL.md
├── BROGI-START.md
├── BROGI-END.md
├── .env              ← .gitignore
├── .env.example
├── .gitignore
├── docker-compose.yml
└── README.md
```

---

## 7. PRAVIDLA PRO DOKUMENTACI A ŘEŠENÍ CHYB

### Při nesrovnalosti nebo pochybnosti:
1. NEJDŘÍV ověřit v oficiální dokumentaci
2. Priorita: oficiální docs > GitHub issues > Stack Overflow > spekulace
3. Pokud docs nestačí → říct Pavlovi explicitně, nehádat

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

---

## 9. OMNIFOCUS — PRAVIDLA (🍏 ověřeno)

OmniFocus projekty: `BrogiMatAssistance` (aktivní) + `BrogiMatAssistanceArchive` (done).
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

---

## 10. GIT — VERZOVÁNÍ (🍏 ověřeno)

Schéma tagů: `vROK.MĚSÍC.DEN.PATCH` — nový den = PATCH reset na 0.

Commit:
```applescript
do shell script "cd /Users/pavel/SynologyDrive/001\\ DXP/009\\ BrogiMAT\\ Assistance && /usr/bin/git add . && /usr/bin/git commit -m 'Dev session' && /usr/bin/git push origin main"
```
Tag:
```applescript
do shell script "cd /Users/pavel/SynologyDrive/001\\ DXP/009\\ BrogiMAT\\ Assistance && /usr/bin/git tag -a vYYYY.MM.DD.N -m 'Development version' && /usr/bin/git push origin --tags"
```

---

## 11. DOCKER ZÁLOHY A RESTORE (🍏 dle oficiální Docker dokumentace)

⚠️ `docker cp` na běžící kontejner = nekonzistentní data. Restore bez smazání volume = mix dat.

### BACKUP — PostgreSQL:
```applescript
do shell script "/usr/local/bin/docker exec assistance-postgres pg_dump -U <user> -d assistance --no-owner --clean > /Users/pavel/SynologyDrive/001\\ DXP/009\\ BrogiMAT\\ Assistance/backup/snapshots/YYYYMMDD/postgres_YYYYMMDD.sql"
```

### Backup checklist (při "commitni"):
1. pg_dump → `backup/snapshots/YYYYMMDD/postgres_YYYYMMDD.sql`
2. Ověřit soubory
3. git commit + push + tag + push --tags

---

## 12. CREDENTIALS — ŠABLONA

`.env` je v `.gitignore` — nikdy necommitovat. `.env.example` commitovat bez hodnot.
Viz `.env.example` v rootu projektu.

### ⚠️ Kritická pravidla:
1. JWT tokeny v osascript vždy přes Python soubor.
2. Location webhook token — uložit v password manageru.

---

*Verze: 1.0 | Aktualizováno: 2026-03-26*

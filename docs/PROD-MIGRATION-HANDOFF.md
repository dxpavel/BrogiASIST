# BrogiASIST — PROD Migration Handoff Prompt
# Připraveno: 2026-04-26 | Pro: novou session

---

## KONTEXT PROJEKTU — přečti nejdřív

Před zahájením práce přečti tyto dokumenty:
- `/Users/pavel/SynologyDrive/001 DXP/009 BrogiASIST/docs/brogiasist-architecture-v1.md`
- `/Users/pavel/SynologyDrive/001 DXP/009 BrogiASIST/docs/brogiasist-lessons-learned-v1.md`
- `/Users/pavel/SynologyDrive/001 DXP/009 BrogiASIST/docs/brogiasist-infrastructure-v1.md`
- `/Users/pavel/SynologyDrive/001 DXP/009 BrogiASIST/docs/brogiasist-data-dictionary-v1.md`

---

## KOMUNIKAČNÍ PRAVIDLA (povinné)

Pavel má Asperger + ADHD. Vždy:
- Strukturovaně, bez keců a omáčky
- Jedna otázka najednou
- Označovat: 🍏 hotovo/ok | 🍎 problém/chyba | 🐒 riziko/pozor | ⚠️ varování
- Před implementací UI/architektury: nejdřív navrhni, počkej na souhlas
- Před prací: vždy zkontroluj zdrojový kód / soubory, nepředpokládej

---

## TVŮJ ÚKOL V TÉTO SESSION

**Přenést BrogiASIST z DEV (MacBook Pro) na PROD (BrogiServer + PajaAppleStudio).**

---

## ARCHITEKTURA PROD (klíčové)

```
BrogiServer (os01.dxpsolutions.cz)     PajaAppleStudio (10.55.2.117)
─────────────────────────────────      ──────────────────────────────
PostgreSQL (Docker)                     Apple Bridge (FastAPI, launchd)
ChromaDB (Docker)                       → OmniFocus, Notes, Reminders
Dashboard WebUI (Docker)                → složka ~/Desktop/BrogiAssist/
Scheduler (Docker)                      (žádná DB, žádná AI)
Ollama / Llama3.2 (Docker nebo system)
```

Apple Bridge URL na BrogiServeru: `http://10.55.2.117:9100`
Ollama URL: `http://localhost:11434` (běží přímo na BrogiServeru)

---

## SSH PŘÍSTUPY (ověřeno fungující)

```bash
# BrogiServer (Linux, root)
ssh forpsi-root
# = ssh root@os01.dxpsolutions.cz -i ~/.ssh/brogibr_ed25519

# PajaAppleStudio (macOS)
ssh dxpavel@10.55.2.117
```

---

## CO JIŽ VÍME ZE SIMULACE

### BrogiServer — stav
- OS: Linux RHEL9, Docker 29.4.0 ✅
- CPU: 4× AMD EPYC, RAM: 7.5GB (2.2GB free), Disk: 36GB free
- Porty 9000/9001/8000/5432 volné ✅
- Adresář připraven: `/opt/brogiasist` ✅
- BrogiASIST zatím neexistuje (fresh start) ✅
- Ollama: není nainstalovaná — **NUTNO NAINSTALOVAT**

### PajaAppleStudio — stav
- OS: macOS 26.3, Python 3.9.6 ✅
- Docker: není (Apple Bridge ho nepotřebuje) ✅
- Apple Bridge: NESPUŠTĚNÝ (existuje jen starý `com.brogimat.webhook.plist`)
- Synology Drive: mountován jako `/Volumes/DXPAVEL DRIVE` ale **nepřístupný přes SSH** (Full Disk Access)
- Desktop: nepřístupný přes SSH (Operation not permitted) — **nutný Full Disk Access pro terminal/SSH**
- LaunchAgents existující: `com.brogimat.webhook.plist` (starý, nesouvisí)

### Data na DEV
- PostgreSQL dump: ~4.2 MB
- ChromaDB: data v Docker volume `009brogiasist_chroma_data`
- SQL migrace: soubory `sql/001_init.sql` … `sql/010_imap_status.sql` + chybí `011_claude_sender_verdicts.sql`

### Kritická zjištění
1. **Python 3.9.6** na Apple Studiu — `str | None` type hints v kódu nebudou fungovat (Python 3.10+). Nutno zkontrolovat apple-bridge/main.py.
2. **Full Disk Access** na Apple Studiu — SSH (bash/python) potřebuje FDA pro přístup k Desktopu, Contacts, Calendar. Bez toho Apple Bridge selže.
3. **Ollama** na BrogiServeru — není, nutno nainstalovat před startem scheduleru.
4. **ChromaDB migrace** — embedding model `nomic-embed-text` musí být dostupný na BrogiServeru (přes Ollama) pro re-embedding.
5. **Attachment složka** — na DEV je bind mount `/Users/pavel/Desktop/OmniFocus:/app/attachments`. Na PROD:
   - BrogiServer scheduler uloží přílohu lokálně
   - Pošle obsah base64 na Apple Bridge
   - Bridge uloží do `~/Desktop/BrogiAssist/` na Apple Studiu
   - Tato změna vyžaduje úpravu `telegram_callback.py` + `apple-bridge/main.py`

---

## POSTUP MIGRACE (v tomto pořadí)

### FÁZE 1 — PajaAppleStudio: Apple Bridge

**1a. Full Disk Access pro Terminal**
- Pavel musí ručně: System Settings → Privacy & Security → Full Disk Access → přidat Terminal
- Bez toho selžou JXA skripty pro Calendar, Contacts

**1b. Zkopírovat apple-bridge na Apple Studio**
```bash
# Z MacBook Pro:
scp -r "/Users/pavel/SynologyDrive/001 DXP/009 BrogiASIST/services/apple-bridge/main.py" dxpavel@10.55.2.117:~/brogiasist-bridge/
scp "/Users/pavel/SynologyDrive/001 DXP/009 BrogiASIST/services/apple-bridge/requirements.txt" dxpavel@10.55.2.117:~/brogiasist-bridge/
scp "/Users/pavel/SynologyDrive/001 DXP/009 BrogiASIST/services/apple-bridge/run.sh" dxpavel@10.55.2.117:~/brogiasist-bridge/
```

**1c. Opravit Python 3.9 kompatibilitu v main.py**
- Nahradit `str | None` za `Optional[str]` (from typing import Optional)
- Zkontrolovat všechny type hints

**1d. Vytvořit PROD launchd plist na Apple Studiu**
```bash
ssh dxpavel@10.55.2.117 "mkdir -p ~/brogiasist-bridge"
# Vytvořit ~/Library/LaunchAgents/cz.brogiasist.apple-bridge.plist
# s cestami pro dxpavel (ne pavel)
```

**1e. Vytvořit BrogiAssist složku na Desktopu**
```bash
ssh dxpavel@10.55.2.117 "mkdir -p ~/Desktop/BrogiAssist"
```

**1f. Spustit a otestovat**
```bash
ssh dxpavel@10.55.2.117 "launchctl load ~/Library/LaunchAgents/cz.brogiasist.apple-bridge.plist"
curl http://10.55.2.117:9100/health
curl http://10.55.2.117:9100/omnifocus/tasks | head -c 200
```

---

### FÁZE 2 — BrogiServer: Ollama

**2a. Nainstalovat Ollama**
```bash
ssh forpsi-root "curl -fsSL https://ollama.com/install.sh | sh"
```

**2b. Stáhnout modely**
```bash
ssh forpsi-root "ollama pull llama3.2-vision:11b && ollama pull nomic-embed-text"
# llama3.2:11b potřebuje ~7GB RAM — zkontrolovat po stažení
```

**2c. Ověřit**
```bash
ssh forpsi-root "curl http://localhost:11434/api/tags | python3 -c 'import sys,json; [print(m[\"name\"]) for m in json.load(sys.stdin)[\"models\"]]'"
```

---

### FÁZE 3 — BrogiServer: Docker stack

**3a. Zkopírovat docker-compose + services**
```bash
# Vytvořit PROD docker-compose.yml (bez bind mount OmniFocus, jiné porty)
scp docker-compose.prod.yml forpsi-root:/opt/brogiasist/docker-compose.yml
rsync -av services/ forpsi-root:/opt/brogiasist/services/
```

**3b. PROD .env na BrogiServeru**
Klíčové rozdíly od DEV `.env`:
```env
# Apple Bridge — Apple Studio IP
APPLE_BRIDGE_URL=http://10.55.2.117:9100

# Ollama — lokální na BrogiServeru
OLLAMA_URL=http://host.docker.internal:11434
# nebo pokud Ollama běží jako system service:
OLLAMA_URL=http://172.17.0.1:11434

# Chroma — v Docker síti
CHROMA_HOST=chromadb
CHROMA_PORT=8000

# PostgreSQL — v Docker síti
POSTGRES_HOST=postgres
POSTGRES_PORT=5432

# Přílohy — lokální cesta na BrogiServeru
ATTACHMENTS_DIR=/app/attachments
```

**3c. PROD docker-compose.yml klíčové změny**
```yaml
scheduler:
  volumes:
    - ./logs:/app/logs
    - ./attachments:/app/attachments   # lokální na serveru, NE plocha Apple Studia
  environment:
    APPLE_BRIDGE_URL: http://10.55.2.117:9100
```

**3d. Spustit stack**
```bash
ssh forpsi-root "cd /opt/brogiasist && docker compose up -d"
```

---

### FÁZE 4 — PostgreSQL migrace

**4a. Dump z DEV**
```bash
# Na MacBook Pro:
docker exec brogi_postgres pg_dump -U brogi assistance > /tmp/brogi_dev_dump.sql
scp /tmp/brogi_dev_dump.sql forpsi-root:/opt/brogiasist/
```

**4b. Restore na BrogiServeru**
```bash
ssh forpsi-root "
cd /opt/brogiasist
docker exec -i brogiasist_postgres psql -U brogi assistance < /opt/brogiasist/brogi_dev_dump.sql
"
```

**4c. Spustit chybějící migrace**
```bash
# claude_sender_verdicts tabulka (přidána 2026-04-25, není v SQL souborech)
ssh forpsi-root "docker exec brogiasist_postgres psql -U brogi assistance -c \"
CREATE TABLE IF NOT EXISTS claude_sender_verdicts (
    email TEXT PRIMARY KEY,
    is_spam BOOLEAN NOT NULL,
    reason TEXT,
    verified_at TIMESTAMP DEFAULT NOW()
);
\""
```

---

### FÁZE 5 — ChromaDB migrace

ChromaDB data jsou malá (vector embeddings). Možnosti:
- **Varianta A**: Zkopírovat Docker volume tar (rychlé, ale vyžaduje stejnou verzi Chroma)
- **Varianta B**: Re-embed z PostgreSQL (pomalejší, ale čistší)

Doporučuji **Varianta A**:
```bash
# Na MacBook Pro:
docker run --rm -v 009brogiasist_chroma_data:/data -v /tmp:/backup alpine tar czf /backup/chroma_backup.tar.gz -C /data .
scp /tmp/chroma_backup.tar.gz forpsi-root:/opt/brogiasist/

# Na BrogiServeru (po startu kontejnerů):
docker run --rm -v brogiasist_chroma_data:/data -v /opt/brogiasist:/backup alpine sh -c "cd /data && tar xzf /backup/chroma_backup.tar.gz"
```

---

### FÁZE 6 — Úprava attachment logiky (kód)

Aktuální DEV: scheduler zapíše přílohu na `/app/attachments/` (bind mount → Mac plocha)
PROD problém: Apple Studio plocha není dostupná z BrogiServeru

**Řešení: base64 přes Apple Bridge API**

Změnit `telegram_callback.py` — při `of` akci:
1. Načti attachment z lokálního disku scheduleru
2. Pošli jako base64 v API callu na Apple Bridge
3. Apple Bridge dekóduje + uloží do `~/Desktop/BrogiAssist/`

Změnit `apple-bridge/main.py` — endpoint `/omnifocus/add_task`:
- Přijmout `file_data: list[{filename, content_base64}]`
- Uložit do `~/Desktop/BrogiAssist/`
- Přidat file:// link do OF note

---

### FÁZE 7 — Ověření

```bash
# Health checks
curl http://10.55.2.117:9100/health          # Apple Bridge
curl http://os01.dxpsolutions.cz:9000/       # Dashboard (pokud veřejný)
ssh forpsi-root "docker logs brogiasist_scheduler --tail 20"

# Test TG notifikace
# Počkat 5 minut, měl by přijít email notify

# Test OF action
# Kliknout 2of na TG, zkontrolovat OmniFocus na Apple Studiu/iPhonu
```

---

## CHYBĚJÍCÍ SQL MIGRACE

Tato tabulka existuje v DB ale nemá SQL soubor — nutno vytvořit `sql/011_claude_sender_verdicts.sql`:
```sql
CREATE TABLE IF NOT EXISTS claude_sender_verdicts (
    email TEXT PRIMARY KEY,
    is_spam BOOLEAN NOT NULL,
    reason TEXT,
    verified_at TIMESTAMP DEFAULT NOW()
);
```

---

## RIZIKA A POZOR

| ⚠️ | Co | Dopad |
|---|---|---|
| 🐒 | Python 3.9 na Apple Studiu | type hints `str\|None` selžou → import error |
| 🐒 | Full Disk Access pro SSH/Terminal | bez toho JXA Calendar/Contacts selže |
| 🐒 | Ollama RAM | llama3.2-vision:11b ~7GB, server má 2.2GB free → nutno ověřit po startu |
| 🐒 | IMAP IDLE paralelní běh | pokud DEV a PROD běží současně → duplikátní actions na TG |
| ⚠️ | DEV vypnout před PROD spuštěním | jinak 2× TG notifikace, 2× IMAP akce |
| ⚠️ | Přílohy bind mount | DEV má `/Users/pavel/Desktop/OmniFocus`, PROD potřebuje base64 refactor |

---

## PRVNÍ KROKY V SESSION

1. Přečti dokumenty (viz začátek)
2. Ověř SSH přístupy: `ssh forpsi-root "echo OK"` a `ssh dxpavel@10.55.2.117 "echo OK"`
3. Začni FÁZÍ 1 — Apple Bridge na PajaAppleStudio
4. Pokud Apple Bridge funguje → FÁZE 2 (Ollama na BrogiServeru)
5. Postupuj chronologicky, ověřuj každý krok

---

*Připraveno session 2026-04-26. Zdrojový kód: `/Users/pavel/SynologyDrive/001 DXP/009 BrogiASIST/`*

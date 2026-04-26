# BrogiASIST — Handoff prompt pro novou session
# Úkol: DEV → PROD migrace (BrogiPROD container na BrogiServeru + Apple Bridge na Apple Studio)

---

## KROK 1 — PŘEČTI NEJDŘÍV (povinné, v tomto pořadí)

```
/Users/pavel/SynologyDrive/001 DXP/009 BrogiASIST/docs/SESSION-HANDOFF-PROD.md   ← tento soubor
/Users/pavel/SynologyDrive/001 DXP/009 BrogiASIST/docs/PROD-MIGRATION-HANDOFF.md ← detailní postup migrace (autoritativní)
/Users/pavel/SynologyDrive/001 DXP/009 BrogiASIST/docs/BUGS.md                   ← známé problémy, BUG-007 řeš v této session
/Users/pavel/SynologyDrive/001 DXP/009 BrogiASIST/docs/brogiasist-architecture-v1.md
/Users/pavel/SynologyDrive/001 DXP/009 BrogiASIST/docs/brogiasist-infrastructure-v1.md
/Users/pavel/SynologyDrive/001 DXP/009 BrogiASIST/docs/brogiasist-lessons-learned-v1.md
```

---

## KROK 2 — KOMUNIKAČNÍ PRAVIDLA (absolutní)

Pavel má Asperger + ADHD. Tato pravidla jsou povinná vždy:

- **Strukturovaně, bez omáčky a keců**
- **Jedna otázka najednou** — nikdy víc
- **Nejdřív se zeptej, pak implementuj** — nikdy nerozhoduj sám
- **Nikdy se nevrhej na implementaci bez odsouhlasení** — ani když si myslíš že víš
- **Označovat**: 🍏 ok/hotovo | 🍎 problém | 🐒 riziko | ⚠️ varování
- **Před UI/architekturou**: navrhni → počkej na souhlas → pak dělej
- **Před prací**: vždy přečti zdrojový kód, nikdy nepředpokládej co tam je
- **Žádné autonomní změny** — reakce na screenshot/komentář ≠ pokyn implementovat

---

## KROK 3 — VÝCHOZÍ STAV (commit `9eaba36`, větev `1`, verze 1.1)

DEV běží lokálně (kontejnery `brogi_postgres`, `brogi_scheduler`, `brogi_dashboard`, `brogi_chromadb`). Apple Bridge běží na MacBook hostu přes launchd. Vše hotové, otestované, dokumentované.

**V této session:** Pavel chce DEV zastavit a stejnou aplikaci rozjet jako **BrogiPROD** na **BrogiServer** (Forpsi VPS, RHEL9) + Apple Bridge na **PajaAppleStudio** (10.55.2.117). Po přepnutí DEV stack zhasnout.

---

## KROK 4 — ÚKOL TÉTO SESSION

### 4a. Pre-flight checks (než cokoli vypneš)

1. **Konektivita BrogiServer ↔ Apple Studio** — toto je KRITICKÉ rozhodnutí:
   - BrogiServer běží na Forpsi VPS (veřejná IP)
   - Apple Studio je v Pavlově domácí LAN (10.55.2.117)
   - **Jak BrogiServer dosáhne 10.55.2.117?** VPN? SSH tunel? Reverse proxy?
   - Bez vyřešení tohoto **PROD nefunguje** (scheduler nezavolá Apple Bridge)
   - **Zeptej se Pavla** dřív než cokoli začneš
2. **Disk space** na BrogiServer pro PostgreSQL + ChromaDB + attachments cache
3. **Bezpečnost `.env`** — `git log --all --full-history -- .env` musí být prázdný
4. **DNS / WebUI přístup** — chce Pavel veřejný subdoména pro dashboard? (např. `brogiasist.dxpsolutions.cz`) Nebo jen přes SSH tunel?

### 4b. Migrace dle `PROD-MIGRATION-HANDOFF.md` (autoritativní postup)

Postup je v dokumentu rozdělen do fází (Apple Studio bridge, BrogiServer Docker stack, data migrace, přepnutí). **Drž se ho** — Pavel ho psal a checknul.

### 4c. BUG-007 fix součástí této session (povinné)

Při tvorbě PROD docker-compose:
- **NEdávat** bind mount `./Desktop/OmniFocus:/app/attachments` (nedává smysl na Linux serveru)
- **Místo toho:** lokální Linux volume `./attachments:/app/attachments`
- Upravit `services/ingest/ingest_email.py` aby `attachments.storage_path` na PROD obsahoval kontejnerovou cestu (žádný replace na Mac path) — viz BUG-007 v `BUGS.md`
- Upravit `services/ingest/telegram_callback.py:_read_attachments_b64` — pokud `_HOST_PREFIX` není v cestě, číst přímo (zpětně kompatibilní s DEV)
- Po PROD přepnutí: Pavel uvidí přílohy **jen v `~/Desktop/BrogiAssist/`** na Apple Studio

### 4d. Telegram offset

⚠️ **Kritické:** TG callback offset je v `config` tabulce (`tg_callback_offset`). Pokud DEV i PROD oba runují TG polling se starým offsetem, vznikne **duplicate notification**.

Postup:
1. Před přepnutím: zastavit DEV scheduler (`docker compose down scheduler` na DEV)
2. Migrovat `config` tabulku jako součást PG dumpu
3. PROD scheduler nahodit AŽ PO completed migraci

### 4e. IMAP IDLE — duplicate ingestu hrozí

⚠️ Stejně jako TG offset:
- DEV scheduler má 8 IMAP IDLE listenerů
- Pokud PROD nahodím dřív než DEV vypnu → 2× IDLE na stejných účtech → duplicate inserts (na ON CONFLICT DO UPDATE OK, ale zbytečně)
- Pořadí: **vypnout DEV scheduler → migrovat data → spustit PROD scheduler**
- Dashboard a Postgres na DEV mohou doběhnout, jen scheduler je critical-section

### 4f. Ollama na BrogiServeru

Není tam nainstalována. Před migraci scheduleru:
```bash
ssh forpsi-root
# Install Ollama (curl + script dle docs)
ollama pull llama3.2-vision:11b
ollama pull nomic-embed-text
```
Bez modelů scheduler `classify_emails` selže.

### 4g. ChromaDB collection migrace

`email_actions` collection (Pavlovy učené vzory) musí přijít přes export/import:
1. Na DEV: dump přes ChromaDB HTTP API (`/api/v1/collections/email_actions/get` s `include=["embeddings","documents","metadatas","ids"]`)
2. Save jako JSON
3. Na PROD: po nahození ChromaDB → import přes `/upsert`
4. Re-embedding přes `nomic-embed-text` na PROD Ollamě **NENÍ TŘEBA** pokud přenášíš embeddings (jsou stejné)

### 4h. Apple Bridge na Apple Studio

- Python 3.9.6 na Apple Studio — **bez `str | None` syntax** (lesson #11). Možná upgrade na Python 3.11+ přes Homebrew? Nebo úprava kódu?
- Full Disk Access pro Terminal/Python (jinak Notes/Calendar/Contacts selžou)
- launchd plist: zkopírovat ze `services/apple-bridge/cz.brogiasist.apple-bridge.plist`, upravit cesty
- `~/Desktop/BrogiAssist/` musí existovat (`mkdir -p`)

### 4i. Po přepnutí — verifikace

1. `curl http://10.55.2.117:9100/health` z BrogiServeru
2. `curl http://os01.dxpsolutions.cz:9000/` (nebo přes proxy) — dashboard live
3. TG: pošli si testovací email, sleduj zda přijde notifikace
4. OF: klik OF, ověř že vznikl task na Apple Studio + soubor na `~/Desktop/BrogiAssist/`
5. Logy 30 min — žádný error loop

---

## KROK 5 — CO ZVAŽ NAVÍC (Pavlovy vstupy potřebné)

| Téma | Otázka pro Pavla |
|---|---|
| **VPN** | Jak BrogiServer dosáhne Apple Studio? (kritické rozhodnutí) |
| **DNS** | Veřejný subdomain pro WebUI, nebo jen SSH? |
| **HTTPS** | Let's Encrypt na nginx? |
| **Backups** | PG dump kam (Synology NAS přes rsync)? Frekvence? |
| **Monitoring** | Jak Pavla notify když PROD spadne? Telegram bot zprávy o errors? |
| **Rollback** | Pokud PROD selže — vrátit se na DEV (ano/ne)? |
| **Downtime window** | Kdy migraci provést (ne v pracovní době)? |
| **Log rotation** | logrotate na BrogiServer pro `/app/logs/`? |
| **Disk monitoring** | Telegram alert při >80 % full? |

---

## KROK 6 — CO NEDĚLAT V TÉTO SESSION

- ❌ Nezakládat nové větve bez ptaní (možná chce branch `prod-migration` nebo `2`)
- ❌ Neřešit BUG-001 (refaktor `_email_action`) — odděleno
- ❌ Neřešit BUG-004/005 IMAP MOVE permanentní fix — mitigace funguje
- ❌ Neřešit BUG-006 (12 ztracených emailů) — Pavel řekl, ručně
- ❌ Žádné OmniJS experimenty — zatím ne
- ❌ Nemazat DEV stack před tím, než PROD funguje a ověříš
- ❌ `git push` nebo `merge do main` bez explicitního pokynu
- ❌ Ne instalovat / měnit nic na BrogiServeru bez pokynu

---

## KROK 7 — NA KONCI SESSION

1. Update `CONTEXT-NEW-CHAT.md` — co teď běží na PROD, co bylo migrováno
2. Update `DOC-MAP.md` — pokud vznikly nové dokumenty
3. Update `BUGS.md` — BUG-007 status FIXED, případné nové bugy z PROD
4. Update `brogiasist-infrastructure-v1.md` — sekce DEV označit jako „archive", PROD jako live
5. Commit do nové větve nebo do `1`, dle dohody

---

*Vytvořeno 2026-04-26 v 1.1 finalizaci. Commit `9eaba36` na větvi `1`.*
*DEV stack běží do okamžiku PROD switchu — počítej s tím že Pavel ho během session vypne.*

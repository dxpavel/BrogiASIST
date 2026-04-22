---
Název: PROJECT-BOOTSTRAP-STANDARD
Soubor: 999 DEVELOPMENT/CLAUDE-SETUP/PROJECT-BOOTSTRAP-STANDARD.md
Verze: 1.1
Poslední aktualizace: 2026-03-17
Popis: Standard pro zakládání nových projektů — adresáře, soubory, placeholdery, DOC-MAP, YAML hlavičky
Změněno v: §3.3 — všechny standardní docs POVINNÉ jako placeholdery při bootstrapu
---

# PROJECT-BOOTSTRAP-STANDARD
# Standard pro zakládání projektové struktury
# Verze: 1.0 | 2026-03-17

---

## 1. PŘEHLED

Tento dokument definuje:
- Jaké adresáře se vytváří při založení nového projektu
- Jaké soubory jsou POVINNÉ v každém projektu
- Jak se soubory pojmenovávají
- Jak vypadá placeholder (prázdný soubor s hlavičkou)
- Jak se plní DOC-MAP
- Formát YAML hlavičky

---

## 2. ADRESÁŘOVÁ STRUKTURA

Při bootstrapu se vytvoří tato struktura:

```
<CCC NAZEV-PROJEKTU>/
│
├── docs/                        ← veškerá dokumentace
│   ├── modules/                 ← modulová dokumentace (projektově specifická)
│   ├── DOC-MAP.md               ← POVINNÝ — centrální katalog dokumentace
│   ├── CONTEXT-NEW-CHAT.md      ← POVINNÝ — kontext pro nový chat
│   └── LESSONS-LEARNED.md       ← POVINNÝ — poučení z praxe
│
├── archive/                     ← JEDINÝ archive v celém projektu
│
├── workflows/                   ← n8n workflow JSON exporty
├── scripts/
│   ├── setup/                   ← setup skripty
│   ├── maintenance/             ← údržbové skripty
│   └── debug/                   ← debug skripty
├── tests/                       ← testy
├── sql/                         ← SQL migrace, seed data
├── config/                      ← konfigurace (ne .env)
├── healthcheck/                 ← health check skripty
├── storage/                     ← runtime data (.gitignore)
├── logs/                        ← logy (.gitignore)
├── backup/
│   └── snapshots/               ← zálohy (pg_dump, volume tar)
├── tmp/                         ← dočasné soubory (.gitignore)
│
├── GLOBAL-SKILL.md              ← POVINNÝ — pravidla projektu
├── BROGI-START.md               ← POVINNÝ — startovní procedura session
├── BROGI-END.md                 ← POVINNÝ — ukončovací procedura session
├── .env                         ← credentials (.gitignore)
├── .env.example                 ← šablona bez hodnot (commitovat)
├── .gitignore
├── docker-compose.yml           ← pokud projekt používá Docker
└── README.md
```

### Pravidla:
- `archive/` je JEN v rootu projektu — NIKDY v docs/, scripts/ ani jinde
- `docs/` NEMÁ podadresář `core/` — soubory jsou přímo v docs/
- `docs/modules/` — pro modulovou dokumentaci specifickou pro projekt
- `<CCC>` = třímístné číslo projektu (001, 007, 008...)

---

## 3. POVINNÉ SOUBORY — PŘEHLED

### 3.1 Root soubory (mimo docs/)

| Soubor | Typ | Vytvořit při bootstrapu | Popis |
|---|---|---|---|
| `GLOBAL-SKILL.md` | pravidla | ✅ kopie z 999 DEVELOPMENT + úprava pro projekt | Pravidla projektu — nástroje, limity, konvence |
| `BROGI-START.md` | procedura | ✅ šablona + úprava cest | Startovní procedura — co provést na začátku session |
| `BROGI-END.md` | procedura | ✅ šablona + úprava cest | Ukončovací procedura — lessons learned, context, commit |
| `README.md` | info | ✅ placeholder | Základní popis projektu |
| `.env.example` | config | ✅ šablona | Credentials šablona bez hodnot |
| `.gitignore` | config | ✅ šablona | storage/ logs/ tmp/ .env *.log __pycache__/ |

### 3.2 Soubory v docs/

| Soubor | Typ | Vytvořit při bootstrapu | Popis |
|---|---|---|---|
| `docs/DOC-MAP.md` | katalog | ✅ s tabulkou povinných souborů | Centrální katalog dokumentace |
| `docs/CONTEXT-NEW-CHAT.md` | kontext | ✅ placeholder se strukturou | Kontext pro nový chat — stav, cesty, problémy |
| `docs/LESSONS-LEARNED.md` | lekce | ✅ placeholder se strukturou | Poučení z praxe — lekce z každé session |

### 3.3 Standardní soubory v docs/ (POVINNÉ při bootstrapu jako placeholdery)

Tyto soubory se vytváří VŽDY při bootstrapu — i když ještě nemají obsah.
Prázdný placeholder = YAML hlavička + nadpis + text "(zatím prázdné — doplnit při implementaci)".
Důvod: musí být jasně vidět, že informace CHYBÍ — ne že dokument neexistuje.
Při vzniku obsahu se zapíší do DOC-MAP.md s aktualizovanou verzí.

| Typ souboru | Pojmenování | Popis |
|---|---|---|
| Systémový popis | `<projekt>-system-popis-v1.md` | Co systém dělá, architektura, dataflow |
| WebUI specifikace | `<projekt>-webui-spec-v1.md` | Obrazovky, komponenty, UX flow |
| Datový slovník | `<projekt>-data-process-dictionary-v1.md` | DB/datové struktury, typy, vztahy, procesy |
| Design system | `<projekt>-design-system-v1.md` | Barvy, typografie, komponenty, zprávy |
| API reference | `<projekt>-api-reference-v1.md` | Endpointy, request/response, JSON schema |
| Infrastruktura | `<projekt>-infrastructure-v1.md` | Stack, kontejnery/servery, porty, sítě, volumes |
| Workflows | `<projekt>-workflows-v1.md` | Automatizace, triggery, vstupy/výstupy |
| Credentials | `<projekt>-credentials-v1.md` | Přístupy, klíče, porty |
| Modulový dokument | `docs/modules/<modul>.md` | Popis modulu — účel, API, datový model (dle potřeby) |

### Pravidla pojmenování:
- `<projekt>` = název projektu malými písmeny s pomlčkami (např. `brogimat-v5`)
- Všechny názvy malými písmeny, pomlčky jako oddělovač
- `v<N>` = verze dokumentu (ne verze projektu)
- Při nové verzi: starý soubor → `archive/`, nový soubor v docs/
- Soubory bez verzování (LESSONS-LEARNED, CONTEXT-NEW-CHAT, DOC-MAP) se přepisují na místě

---

## 4. YAML HLAVIČKA — STANDARD

Každý .md soubor v projektu MUSÍ mít YAML hlavičku na začátku souboru.

### Formát:
```yaml
---
Název: <lidsky čitelný název>
Soubor: <relativní cesta od rootu projektu>
Verze: <číslo verze>
Poslední aktualizace: <YYYY-MM-DD>
Popis: <1 věta — co soubor obsahuje>
Změněno v: <popis poslední změny>
---
```

### Příklad:
```yaml
---
Název: LESSONS-LEARNED
Soubor: docs/LESSONS-LEARNED.md
Verze: 1.0
Poslední aktualizace: 2026-03-17
Popis: Poučení z praxe — lekce z každé session
Změněno v: vytvořen (bootstrap projektu)
---
```

### Pravidla:
- YAML hlavička je JEDINÉ místo kde je verze souboru — žádná duplicitní patička na konci
- `Soubor:` = relativní cesta od rootu projektu (ne absolutní)
- `Verze:` = verze dokumentu, ne verze projektu
- `Změněno v:` = stručný popis POSLEDNÍ změny (ne celá historie)
- Při každé editaci: aktualizovat `Poslední aktualizace` a `Změněno v`

---

## 5. PLACEHOLDER — ŠABLONA PRO PRÁZDNÉ SOUBORY

Při bootstrapu se vytvářejí soubory jako placeholdery — mají YAML hlavičku a základní strukturu, ale prázdný obsah.

### 5.1 CONTEXT-NEW-CHAT.md placeholder:
```markdown
---
Název: CONTEXT-NEW-CHAT
Soubor: docs/CONTEXT-NEW-CHAT.md
Verze: 1.0
Poslední aktualizace: <DATUM>
Popis: Kontext pro nový chat — co projekt dělá, aktuální stav, klíčové cesty, otevřené problémy
Změněno v: vytvořen (bootstrap projektu)
---

# CONTEXT-NEW-CHAT — <NazevProjektu>

---

## Co projekt je
<1-2 věty — co projekt dělá>

## Aktuální stav
- Co běží: —
- Co se řeší: —
- Co je rozbité: —

## Klíčové cesty
- Root: /Users/pavel/SynologyDrive/001 DXP/<CCC NAZEV-PROJEKTU>/
- Dokumentace: `<ROOT>/docs/`
- Katalog dokumentace: `<ROOT>/docs/DOC-MAP.md`
- Moduly dokumentace: `<ROOT>/docs/modules/`
- Archive: `<ROOT>/archive/`

## Na čem se pracuje
—

## Otevřené problémy
—

## Lessons learned
→ Viz `docs/LESSONS-LEARNED.md`

## Poslední rozhodnutí
| Datum | Rozhodnutí |
|---|---|
| <DATUM> | Projekt založen |
```

### 5.2 LESSONS-LEARNED.md placeholder:
```markdown
---
Název: LESSONS-LEARNED
Soubor: docs/LESSONS-LEARNED.md
Verze: 1.0
Poslední aktualizace: <DATUM>
Popis: Poučení z praxe — lekce z každé session
Změněno v: vytvořen (bootstrap projektu)
---

# LESSONS-LEARNED — <NazevProjektu>
# Aktualizovat po každé session.

---

(prázdné — doplnit po první session)
```

### 5.3 DOC-MAP.md placeholder:
```markdown
---
Název: DOC-MAP
Soubor: docs/DOC-MAP.md
Verze: 1.0
Poslední aktualizace: <DATUM>
Popis: Centrální katalog dokumentace — přehled všech souborů, verzí, popisů
Změněno v: vytvořen (bootstrap projektu)
---

# DOC-MAP — <NazevProjektu>
# Centrální katalog dokumentace

---

## docs/

| Soubor | Verze | Poslední aktualizace | Popis |
|---|---|---|---|
| DOC-MAP.md | 1.0 | <DATUM> | Centrální katalog dokumentace |
| CONTEXT-NEW-CHAT.md | 1.0 | <DATUM> | Kontext pro nový chat — stav, cesty, problémy |
| LESSONS-LEARNED.md | 1.0 | <DATUM> | Poučení z praxe — lekce z každé session |

## docs/modules/

(prázdné — doplnit při vzniku modulů)

## Root soubory (mimo docs/)

| Soubor | Verze | Poslední aktualizace | Popis |
|---|---|---|---|
| GLOBAL-SKILL.md | 1.0 | <DATUM> | Pravidla projektu — nástroje, limity, konvence |
| BROGI-START.md | 1.0 | <DATUM> | Startovní procedura session |
| BROGI-END.md | 1.0 | <DATUM> | Ukončovací procedura session |
```

---

## 6. DOC-MAP — PRAVIDLA ÚDRŽBY

### Kdy aktualizovat DOC-MAP:
- Nový soubor přidán do docs/ nebo docs/modules/ → přidat řádek
- Soubor přesunut do archive/ → odebrat řádek, případně přidat do sekce archive
- Verze nebo datum souboru se změnily → aktualizovat příslušný řádek

### Struktura DOC-MAP:
DOC-MAP má tyto sekce (v tomto pořadí):
1. `## docs/` — hlavní dokumenty
2. `## docs/modules/` — modulové dokumenty
3. `## Root soubory (mimo docs/)` — GLOBAL-SKILL, BROGI-START, BROGI-END
4. `## archive/` (volitelné) — přesunuté/zastaralé soubory

### Sloupce tabulky:
| Sloupec | Zdroj | Pravidlo |
|---|---|---|
| Soubor | název souboru | jen název, ne celá cesta |
| Verze | YAML hlavička souboru `Verze:` | musí odpovídat |
| Poslední aktualizace | YAML hlavička souboru `Poslední aktualizace:` | musí odpovídat |
| Popis | YAML hlavička souboru `Popis:` | musí odpovídat |

### Konzistence:
- DOC-MAP je SEKUNDÁRNÍ zdroj — primární je YAML hlavička v každém souboru
- Při neshodě platí YAML hlavička souboru
- DOC-MAP se aktualizuje ve stejném kroku jako soubor (ne zpětně)

---

## 7. BOOTSTRAP PROCEDURA — KROK ZA KROKEM

Když Pavel napíše:
```
Zakládám nový projekt [NAZEV], složka: /Users/pavel/SynologyDrive/001 DXP/[CCC NAZEV-SLOZKY]
```

### Kroky:

**Krok 1 — Extrakce názvu**
- Ze složky `007 BROGIMAT-V5` → projekt `BrogiMAT-V5`
- Ze složky `008 BrogiDevTeam` → projekt `BrogiDevTeam`

**Krok 2 — Vytvoření adresářů**
Dle sekce 2 tohoto dokumentu. Nástroj: `Desktop Commander:create_directory`

**Krok 3 — Vytvoření povinných souborů**
Dle sekce 3.1 a 3.2. Šablony dle sekce 5. Nástroj: `Desktop Commander:write_file`

Pořadí vytváření:
1. `.gitignore` + `.env.example` + `README.md`
2. `GLOBAL-SKILL.md` (kopie ze `999 DEVELOPMENT/CLAUDE-SETUP/` + úprava pro projekt)
3. `BROGI-START.md` (šablona + úprava cest na aktuální projekt)
4. `BROGI-END.md` (šablona + úprava cest na aktuální projekt)
5. `docs/CONTEXT-NEW-CHAT.md` (placeholder dle 5.1)
6. `docs/LESSONS-LEARNED.md` (placeholder dle 5.2)
7. `docs/DOC-MAP.md` (placeholder dle 5.3)

**Krok 4 — GitHub repo**
```
github:create_repository → github:push_files (initial commit)
```

**Krok 5 — OmniFocus projekty**
```
omnifocus-enhanced:add_project → <NazevProjektu>
omnifocus-enhanced:add_project → <NazevProjektu>Archive
```

**Krok 6 — První commit + push + tag**
Dle GLOBAL-SKILL.md §15 (Git verzování).

---

## 8. ŽIVOTNÍ CYKLUS DOKUMENTU

```
Bootstrap → placeholder v docs/ + řádek v DOC-MAP
    ↓
Obsah se plní → aktualizace YAML hlavičky + DOC-MAP
    ↓
Nová verze → starý soubor do archive/, nový v docs/, DOC-MAP update
    ↓
Zastaralý → přesun do archive/, odebrání z DOC-MAP
```

### Verzování souborů:
- Soubory s `v<N>` v názvu (system-popis-v10, WebUI-spec-v0_6) → při velké změně: nová verze, starý do archive/
- Soubory bez verze v názvu (LESSONS-LEARNED, CONTEXT-NEW-CHAT, DOC-MAP) → přepisují se na místě, verze jen v YAML

### Archive pravidla:
- `archive/` je JEN v rootu projektu
- Přesunuté soubory se NEMAŽOU — jen přesouvají
- V archive/ se soubory NEeditují
- Archive NENÍ v DOC-MAP (volitelně může mít vlastní sekci)

---

## 9. CHECKLIST — VERIFIKACE PO BOOTSTRAPU

Po založení projektu ověřit:

- [ ] Všechny adresáře z sekce 2 existují
- [ ] Všechny povinné soubory z sekce 3 existují
- [ ] Každý .md soubor má YAML hlavičku (sekce 4)
- [ ] DOC-MAP obsahuje řádek pro každý soubor v docs/
- [ ] Žádný soubor nemá duplicitní patičku verze na konci
- [ ] BROGI-START.md čte GLOBAL-SKILL.md z LOKÁLNÍHO projektu (ne z 999)
- [ ] GitHub repo vytvořeno a initial commit pushnut
- [ ] OmniFocus projekty existují (<Projekt> + <Projekt>Archive)
- [ ] .gitignore obsahuje: storage/ logs/ tmp/ .env *.log __pycache__/

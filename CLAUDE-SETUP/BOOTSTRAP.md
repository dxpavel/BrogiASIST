# BOOTSTRAP.md
# Spustit na začátku každého NOVÉHO projektu
# Verze: 1.0 | 2026-03-14

---

## CO TENTO SOUBOR DĚLÁ

Když Pavel řekne "bootstrap projekt [název]", já:
1. Načtu GLOBAL-SKILL.md (globální pravidla)
2. Zjistím live prostředí (Docker, MCP, cesty)
3. Vytvořím projektovou složku se strukturou
4. Vytvořím GitHub repo
5. Vytvořím CONTEXT-NEW-CHAT.md pro projekt
6. Vytvořím OmniFocus projekty pro tracking

---

## BOOTSTRAP PROMPT (Pavel kopíruje a spustí)

```
Spouštím nový projekt. Název: [NAZEV_PROJEKTU]
Složka: /Users/pavel/SynologyDrive/001 DXP/[CISLO] [NAZEV_PROJEKTU]

Proveď bootstrap:
1. Načti /Users/pavel/SynologyDrive/001 DXP/999 DEVELOPMENT/CLAUDE-SETUP/GLOBAL-SKILL.md
2. Zjisti live Docker stav
3. Vytvoř složkovou strukturu projektu dle GLOBAL-SKILL.md sekce 11
4. Vytvoř GitHub repo [nazev-projektu] (private)
5. Vytvoř docs/CONTEXT-NEW-CHAT.md
6. Vytvoř OmniFocus projekt [NAZEV_PROJEKTU] a [NAZEV_PROJEKTU]Archive
7. Shrň co bylo vytvořeno
```

---

## CO JÁ PROVEDU (krok za krokem)

### Krok 1 — Načtení GLOBAL-SKILL.md
```
filesystem:read_text_file
  path: /Users/pavel/SynologyDrive/001 DXP/999 DEVELOPMENT/CLAUDE-SETUP/GLOBAL-SKILL.md
```

### Krok 2 — Live Docker stav
```
docker:list-containers
```

### Krok 3 — Vytvoření složkové struktury
Vytvořím všechny složky dle sekce 11 GLOBAL-SKILL.md:
```
<projekt>/docs/core/
<projekt>/docs/modules/
<projekt>/docs/archive/
<projekt>/workflows/archive/
<projekt>/scripts/setup/
<projekt>/scripts/maintenance/
<projekt>/scripts/debug/archive/
<projekt>/scripts/archive/
<projekt>/tests/archive/
<projekt>/sql/archive/
<projekt>/config/archive/
<projekt>/healthcheck/
<projekt>/storage/
<projekt>/logs/
<projekt>/backup/snapshots/
<projekt>/tmp/
```

### Krok 4 — GitHub repo
```
github:create_repository
  name: "[nazev-projektu]"
  private: true
  description: "[popis projektu]"
```

Pak inicializuji git lokálně:
```bash
cd <projekt>
git init
git remote add origin https://github.com/[user]/[nazev-projektu].git
git add .
git commit -m "Initial structure"
git push -u origin main
```

### Krok 5 — CONTEXT-NEW-CHAT.md
Vytvořím `docs/CONTEXT-NEW-CHAT.md` se základní šablonou (viz UPDATE.md pro formát).

### Krok 6 — OmniFocus projekty
```
omnifocus-enhanced:add_project
  name: "[NAZEV_PROJEKTU]"

omnifocus-enhanced:add_project
  name: "[NAZEV_PROJEKTU]Archive"
```

### Krok 7 — Shrnutí
Vypíšu co bylo vytvořeno, co potřebuje ruční zásah.

---

## PO BOOTSTRAPU — Pavel udělá ručně

1. Přidat `.env` soubor (zkopírovat z `.env.example` a doplnit hodnoty)
2. Nahrát `docs/CONTEXT-NEW-CHAT.md` do Project Knowledge v claude.ai
3. Případně přidat projekt do Claude Desktop jako nový Project

---

*Verze: 1.0 | 2026-03-14*

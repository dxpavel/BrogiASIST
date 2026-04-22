# BROGI-START.md
# Zahajovací prompt pro každý nový chat
# Verze: 1.1 | 2026-03-14

---

## Použití

Pavel napíše:
```
Ahoj Brogi, začínáme novou session na [NAZEV_PROJEKTU].
Složka: /Users/pavel/SynologyDrive/001 DXP/[NAZEV_SLOZKY]
```

---

## CO JÁ PROVEDU

### 1 — Globální pravidla
```
filesystem:read_text_file
  /Users/pavel/SynologyDrive/001 DXP/999 DEVELOPMENT/CLAUDE-SETUP/GLOBAL-SKILL.md
```

### 2 — Projektový kontext
```
filesystem:read_multiple_files
  <PROJEKT>/docs/CONTEXT-NEW-CHAT.md
  <PROJEKT>/docs/LESSONS-LEARNED.md
  <PROJEKT>/docs/core/03-docker.md
```

### 3 — Live Docker stav
```applescript
do shell script "/usr/local/bin/docker ps --format 'NAME:{{.Names}} PORTS:{{.Ports}} STATUS:{{.Status}}'"
```
Porovnat s `docs/core/03-docker.md` — hlásit rozdíly.

### 4 — Záloha na začátku session
Dle sekce 16 GLOBAL-SKILL.md.

### 5 — OmniFocus tasky
Dle sekce 14 GLOBAL-SKILL.md.

### 6 — Shrnutí pro Pavla
1. Aktuální stav projektu (z CONTEXT-NEW-CHAT.md)
2. Otevřené tasky (z OmniFocus)
3. Rozdíly live Docker vs dokumentace (pokud jsou)
4. Největší otevřené riziko / bug

---

*Verze: 1.1 | 2026-03-14*

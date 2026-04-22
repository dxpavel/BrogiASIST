---
Název: BROGI-START
Soubor: BROGI-START.md
Verze: 1.0
Poslední aktualizace: 2026-03-26
Popis: Startovní procedura session — co provést na začátku session
Změněno v: vytvořen (bootstrap projektu)
---

# BROGI-START.md
# Zahajovací prompt pro každý nový chat na BrogiMatAssistance
# Verze: 1.0 | 2026-03-26

---

## Použití

Pavel napíše:
```
Ahoj Brogi, začínáme novou session na BrogiMatAssistance.
Složka: /Users/pavel/SynologyDrive/001 DXP/009 BrogiMAT Assistance
```

---

## CO JÁ PROVEDU

### 1 — Globální pravidla
```
filesystem:read_text_file
  /Users/pavel/SynologyDrive/001 DXP/009 BrogiMAT Assistance/GLOBAL-SKILL.md
```

### 2 — Projektový kontext
```
filesystem:read_multiple_files
  /Users/pavel/SynologyDrive/001 DXP/009 BrogiMAT Assistance/docs/CONTEXT-NEW-CHAT.md
  /Users/pavel/SynologyDrive/001 DXP/009 BrogiMAT Assistance/docs/LESSONS-LEARNED.md
```

### 3 — Live Docker stav
```applescript
do shell script "/usr/local/bin/docker ps --format 'NAME:{{.Names}} PORTS:{{.Ports}} STATUS:{{.Status}}'"
```
Porovnat s dokumentací — hlásit rozdíly.

### 4 — Záloha na začátku session
Dle GLOBAL-SKILL.md §11.

### 5 — OmniFocus tasky
```
omnifocus-enhanced:filter_tasks → projectName: BrogiMatAssistance
```

### 6 — Shrnutí pro Pavla
1. Aktuální stav projektu (z CONTEXT-NEW-CHAT.md)
2. Otevřené tasky (z OmniFocus)
3. Rozdíly live Docker vs dokumentace (pokud jsou)
4. Největší otevřené riziko / bug

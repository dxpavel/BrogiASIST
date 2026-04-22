# BROGI-END.md
# Ukončovací prompt pro každý chat
# Verze: 1.1 | 2026-03-14

---

## Použití

Pavel napíše:
```
Ukončujeme session na [NAZEV_PROJEKTU].
```

---

## CO JÁ PROVEDU

### 1 — LESSONS-LEARNED
Doplnit do `docs/LESSONS-LEARNED.md`:
```
### Session YYYY-MM-DD — [stručný název]
Co bylo hotovo: ...
Nové lekce (🚨 problém → příčina → fix → pravidlo): ...
Otevřené: ...
```
Pokud žádná nová lekce → jen session log.

### 2 — CONTEXT-NEW-CHAT.md
Aktualizovat `docs/CONTEXT-NEW-CHAT.md` dle šablony v UPDATE.md.

### 3 — Projektová dokumentace
Dle toho co se změnilo:
- `docs/core/03-docker.md` — změna kontejnerů/portů
- `docs/core/04-workflows.md` — nový/změněný workflow
- `docs/core/05-data-dictionary.md` — změna DB schématu
- `docs/core/02-architecture.md` — změna architektury

### 4 — OmniFocus sync
Dle sekce 14 GLOBAL-SKILL.md (done workflow — 3 kroky).

### 5 — Záloha
Dle sekce 16 GLOBAL-SKILL.md.

### 6 — Git commit
Dle sekce 15 GLOBAL-SKILL.md.

### 7 — Přenos do nového chatu (jen pokud práce nedokončena)
Napsat zahajovací prompt s:
- Co zbylo nedokončeno
- Konkrétní první krok
- Relevantní IDs / node names

---

*Verze: 1.1 | 2026-03-14*

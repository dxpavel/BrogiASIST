# UPDATE.md
# Spustit když se změní prostředí projektu
# Verze: 1.0 | 2026-03-14

---

## CO TENTO SOUBOR DĚLÁ

Když Pavel řekne "update projekt" nebo "aktualizuj context", já:
1. Načtu aktuální CONTEXT-NEW-CHAT.md
2. Zjistím live stav (Docker, nové soubory, změny)
3. Aktualizuji CONTEXT-NEW-CHAT.md
4. Pavel nahraje novou verzi do Project Knowledge

---

## UPDATE PROMPT (Pavel kopíruje a spustí)

```
Aktualizuj projekt [NAZEV_PROJEKTU].
Složka: /Users/pavel/SynologyDrive/001 DXP/[CISLO] [NAZEV_PROJEKTU]

Co se změnilo: [Pavel popíše co se změnilo]

Proveď update:
1. Načti docs/CONTEXT-NEW-CHAT.md
2. Zjisti live Docker stav
3. Aktualizuj CONTEXT-NEW-CHAT.md
4. Ulož
```

---

## ŠABLONA CONTEXT-NEW-CHAT.md

```markdown
# CONTEXT-NEW-CHAT — [NAZEV_PROJEKTU]
# Aktualizováno: YYYY-MM-DD

---

## Co projekt je
[1-2 věty co projekt dělá a k čemu slouží]

## Aktuální stav
- Co běží: [seznam]
- Co se řeší: [aktuální problém nebo feature]
- Co je rozbité: [pokud něco]

## Klíčové cesty
- Root: /Users/pavel/SynologyDrive/001 DXP/[CISLO] [NAZEV_PROJEKTU]/
- Docker compose: <ROOT>/docker-compose.yml
- Env: <ROOT>/.env
- Dokumentace: <ROOT>/docs/core/

## Aktivní kontejnery
| Kontejner | Port | Síť |
|---|---|---|
| [nazev] | [port] | [sit] |

## Na čem se pracuje
[Konkrétní task nebo feature]

## Otevřené problémy
- [ ] [problém 1]
- [ ] [problém 2]

## Poslední rozhodnutí
| Datum | Rozhodnutí |
|---|---|
| YYYY-MM-DD | [co bylo rozhodnuto] |
```

---

## KDY AKTUALIZOVAT

✅ Aktualizovat:
- Nový kontejner, workflow, modul, tabulka
- Vyřešený problém
- Změna směru nebo stavu
- Před delší pauzou v práci

❌ NEaktualizovat:
- Chat byl jen dotaz
- Drobná oprava bez dopadu na stav

---

*Verze: 1.0 | 2026-03-14*

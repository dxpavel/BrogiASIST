# CODE AUDIT
> Analýza kódu a n8n workflow na dead code, pozůstatky, duplicity.  
> **Pouze report — žádné mazání bez souhlasu. Vše se archivuje.**

---

## SPUŠTĚNÍ
- **Automaticky:** jako součást `PRE-DEPLOY START` (bod 2)
- **Manuálně:** příkazem `AUDIT START`
- **Povinně:** před každým větším refactorem

---

## 1. DEAD CODE — KÓD

| Typ | Název | Soubor | Řádek | Doporučení |
|-----|-------|--------|-------|------------|
| Funkce | ... | ... | ... | archivovat / smazat |
| Proměnná | ... | ... | ... | archivovat / smazat |
| Import | ... | ... | ... | odebrat |
| Soubor | ... | ... | — | archivovat / smazat |

**Nástroj:** spustit `grep`, statická analýza nebo ESLint/Pylint dle jazyka projektu.

---

## 2. DEAD CODE — n8n WORKFLOW

| Workflow | Problém | Doporučení |
|----------|---------|------------|
| ... | Nikdy se nespouští / deaktivován | archivovat |
| ... | Nod bez výstupu (dead end) | opravit / archivovat |
| ... | Duplicitní workflow se stejnou funkcí | sloučit |
| ... | Webhook bez aktivního listeneru | ověřit / smazat |

- [ ] Všechny aktivní workflow mají error handler?
- [ ] Žádný workflow není pojmenován "test", "copy", "old"?
- [ ] Žádný HTTP Request nod nemá hardcoded URL která by měla být proměnná?

---

## 3. ZOMBIE ZÁVISLOSTI

### 3.1 Nepoužité balíčky
| Balíček | Soubor | Použit v kódu | Doporučení |
|---------|--------|---------------|------------|
| ...     | package.json / requirements.txt | ANO/NE | odebrat |

**Nástroj:** `npm audit` pro Node.js, `pip-audit` nebo `safety` pro Python.

### 3.2 Zastaralé nebo zranitelné balíčky
| Balíček | Aktuální | Nejnovější | CVE | Závažnost | Doporučení |
|---------|----------|------------|-----|-----------|------------|
| ...     | ...      | ...        | ANO/NE | 🔴/🟠/🟡 | aktualizovat |

### 3.3 Docker image
| Image | Aktuální tag | Datum buildu | Zastaralý | Doporučení |
|-------|-------------|-------------|-----------|------------|
| ...   | ...         | ...         | ANO/NE    | aktualizovat |

**Nástroj:** `docker scout cves` nebo `trivy image <název>`.

---

## 4. DUPLICITNÍ KÓD

| Typ | Popis | Výskyt 1 | Výskyt 2 | Doporučení |
|-----|-------|----------|----------|------------|
| Funkce | ... | soubor:řádek | soubor:řádek | refactor |
| Konstanta | ... | soubor:řádek | soubor:řádek | centralizovat do config |
| n8n nod | ... | workflow A | workflow B | vytvořit sdílený sub-workflow |

---

## 5. NEDOSAŽITELNÝ KÓD

| Soubor | Řádek | Typ | Popis | Doporučení |
|--------|-------|-----|-------|------------|
| ... | ... | za return/break | ... | smazat |
| ... | ... | podmínka vždy false | ... | smazat / refactor |

---

## 6. POZŮSTATKY

### 6.1 TODO / FIXME
| Typ | Obsah | Soubor | Řádek | Stáří | Priorita |
|-----|-------|--------|-------|-------|----------|
| TODO | ... | ... | ... | ... | VYSOKÁ/STŘEDNÍ/NÍZKÁ |

### 6.2 Debug výpisy
| Typ | Soubor | Řádek | Doporučení |
|-----|--------|-------|------------|
| console.log | ... | ... | odebrat |
| print | ... | ... | odebrat |

### 6.3 Zakomentovaný kód
| Soubor | Řádky | Odhad stáří | Doporučení |
|--------|-------|------------|------------|
| ... | ... | ... | archivovat / smazat |

---

## 7. TECHNICKÝ DLUH — SOUHRN

| Kategorie | Počet | Nejzávažnější | Odh. čas opravy |
|-----------|-------|--------------|-----------------|
| Dead code (kód) | ... | ... | ... |
| Dead code (n8n) | ... | ... | ... |
| Zombie závislosti | ... | ... | ... |
| Duplicity | ... | ... | ... |
| Pozůstatky | ... | ... | ... |

---

## 8. ARCHIV — ODLOŽENÉ POLOŽKY
> Nic se nesmaže bez souhlasu. Nejistá rozhodnutí jdou sem.

| Položka | Důvod odložení | Datum | Revize |
|---------|---------------|-------|--------|
| ... | ... | ... | ... |

---

## VÝSTUPNÍ REPORT (generuje AI)

```
DATUM: ___
NALEZENÉ POLOŽKY: počet celkem (blocker: X, warning: Y)
KRITICKÉ: seznam nebo "žádné"
LZE POKRAČOVAT K NASAZENÍ: ANO / NE
```

---
*Verze: 2.0 | Stack: n8n + Docker + Synology*

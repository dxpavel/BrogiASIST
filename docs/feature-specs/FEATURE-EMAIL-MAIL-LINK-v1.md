---
Název: FEATURE-EMAIL-MAIL-LINK-v1
Soubor: docs/feature-specs/FEATURE-EMAIL-MAIL-LINK-v1.md
Verze: 1.0
Datum vytvoření: 2026-04-30
Autor: Pavel + Brogi (chat session)
Status: READY-FOR-CODE (zadání pro Claude Code)
Branch: pokračuje na `2`
---

# FEATURE: Email link → Apple Mail.app na index dashboardu

## 1. CÍL (jedna věta)

Přidat na `/` (index dashboard) v sekci **Email — přijaté zprávy** klikatelnou ikonu 📧 mezi sloupcem *Předmět* a *Tagy*, která po kliknutí otevře přesnou zprávu v Apple Mail.app — i pokud je zpráva přesunutá v `BrogiASIST/HOTOVO`, Trashi, nebo špatně zatříděná.

## 2. KONTEXT (proč)

- 🍏 V DB sloupci `email_messages.source_id` je uložené RFC 5322 Message-ID (stabilní identifikátor zprávy).
- 🍏 Apple Mail podporuje URL scheme `message://%3C{Message-ID}%3E` — najde zprávu **napříč všemi složkami** podle Message-ID.
- 🍏 Pavel potřebuje rychlý jump z dashboardu do Mail.app pro ruční opravu chybně zatříděných emailů (incident s `novak@strechy-novak.cz` 2026-04-30 — Pavel emailu nemohl najít manuálně).
- 🐒 *Bonus:* stejný princip později rozšířit na `/ukoly`, `notify_emails.py` (TG) — **NE v této featuře**, jen index.

## 3. ROZSAH (co se mění a co ne)

### V rozsahu (BUDE se měnit)
| Soubor | Změna |
|---|---|
| `services/dashboard/main.py` | SELECT + dict builder pro `email_log` — přidat `source_id` + předgenerovat `mail_url` |
| `services/dashboard/templates/index.html` | colgroup +1 sloupec (24px), header row +1 `<th>`, data row +1 `<td>` s anchorem |

### Mimo rozsah (NEMĚNIT — ZAKÁZÁNO bez další domluvy)
- ❌ `/ukoly` (jiný flow, řešíme potom)
- ❌ Telegram notifikace (`notify_emails.py`)
- ❌ Jakákoliv refaktorizace `get_db_status()` mimo blok email_log
- ❌ Změny stylu/CSS celkového dashboardu mimo nový sloupec
- ❌ Změny v jiných sloupcích (firma, předmět, tagy, čas)
- ❌ Přidání filtrace / řazení / nového UI prvku
- ❌ Změny v `email_messages` schémetu (sloupec `source_id` už existuje)

## 4. PŘESNÉ ZMĚNY V KÓDU

### 4.1 `services/dashboard/main.py`

**Lokace:** funkce `get_db_status()`, blok kolem řádků 78–105 (SELECT pro email_log + dict builder).

**A) SQL — přidat `source_id` na konec SELECTu:**

```python
# PŘED:
cur.execute("""
    SELECT id, mailbox, from_address, subject, sent_at, firma, typ, task_status, is_spam, ai_confidence, human_reviewed
    FROM email_messages
    WHERE is_spam = FALSE
    ORDER BY sent_at DESC NULLS LAST
    LIMIT 100
""")

# PO:
cur.execute("""
    SELECT id, mailbox, from_address, subject, sent_at, firma, typ, task_status, is_spam, ai_confidence, human_reviewed, source_id
    FROM email_messages
    WHERE is_spam = FALSE
    ORDER BY sent_at DESC NULLS LAST
    LIMIT 100
""")
```

**B) Dict builder — přidat `source_id` + `mail_url`:**

Použít helper funkci pro stavbu URL (URL-encode v Pythonu, NE v Jinja2 — Jinja2 v FastAPI defaultně `urlencode` filter nemá).

```python
# Před definicí email_log přidej helper:
import urllib.parse  # přidat k existujícím importům na začátek souboru, pokud tam ještě není

def build_mail_url(source_id):
    """
    Sestaví Apple Mail message:// URL pro otevření zprávy podle Message-ID.
    Vrací None pokud source_id chybí nebo není použitelné.
    Mail.app najde zprávu globálně přes Message-ID — funguje napříč složkami.
    """
    if not source_id:
        return None
    mid = source_id.strip()
    # source_id v DB je obvykle bez závorek <>, ale defenzivně je ošetříme:
    if mid.startswith('<') and mid.endswith('>'):
        mid = mid[1:-1]
    if not mid:
        return None
    # URL-encode (zachovat /), Apple Mail vyžaduje %3C ... %3E kolem encodovaného Message-ID
    encoded = urllib.parse.quote(mid, safe='')
    return f"message://%3C{encoded}%3E"
```

**C) Dict builder — přidat `source_id` + `mail_url` do položky:**

```python
# PŘED:
email_log = [
    {"id": str(r[0]), "mailbox": r[1] or "?", "from_name": extract_name(r[2]),
     "from_address": r[2] or "—",
     "subject": r[3] or "(bez předmětu)", "sent_at": r[4],
     "firma": r[5], "typ": r[6], "task_status": r[7], "is_spam": r[8],
     "confidence": r[9], "human_reviewed": r[10]}
    for r in cur.fetchall()
]

# PO:
email_log = [
    {"id": str(r[0]), "mailbox": r[1] or "?", "from_name": extract_name(r[2]),
     "from_address": r[2] or "—",
     "subject": r[3] or "(bez předmětu)", "sent_at": r[4],
     "firma": r[5], "typ": r[6], "task_status": r[7], "is_spam": r[8],
     "confidence": r[9], "human_reviewed": r[10],
     "source_id": r[11], "mail_url": build_mail_url(r[11])}
    for r in cur.fetchall()
]
```

### 4.2 `services/dashboard/templates/index.html`

**Lokace:** sekce `<!-- Email log — NAHOŘE -->`, blok `<table id="emailTable">` (cca řádek 89–115 v aktuální verzi).

**A) `<colgroup>` — vložit nový `<col style="width:24px">` mezi *Předmět* (auto) a *Tagy* (110px):**

```html
<!-- PŘED: -->
<colgroup><col style="width:22px"><col style="width:16px"><col style="width:20%"><col style="width:auto"><col style="width:110px"><col style="width:60px"></colgroup>

<!-- PO: -->
<colgroup><col style="width:22px"><col style="width:16px"><col style="width:20%"><col style="width:auto"><col style="width:24px"><col style="width:110px"><col style="width:60px"></colgroup>
```

**B) Header row — vložit `<th>` mezi `Předmět` a `Tagy`:**

```html
<!-- PŘED: -->
<tr><th></th><th></th><th>Od</th><th>Předmět</th><th>Tagy</th><th style="text-align:right">Čas</th></tr>

<!-- PO: -->
<tr><th></th><th></th><th>Od</th><th>Předmět</th><th></th><th>Tagy</th><th style="text-align:right">Čas</th></tr>
```

**C) Data row — vložit `<td>` s anchorem mezi `Předmět` `<td>` a `Tagy` `<td>`:**

```html
<!-- PŘED (řádek s předmětem + tagy): -->
<td style="overflow:hidden;text-overflow:ellipsis;font-size:10px">{{ m.subject }}</td>
<td style="white-space:nowrap;overflow:hidden">
  {% if m.typ %}<span class="typ-box {{ tc.get(m.typ, 'typ-info') }}">{{ m.typ }}</span>{% endif %}
  ...

<!-- PO: -->
<td style="overflow:hidden;text-overflow:ellipsis;font-size:10px">{{ m.subject }}</td>
<td style="padding:3px 2px;text-align:center;">
  {% if m.mail_url %}
  <a href="{{ m.mail_url }}"
     onclick="event.stopPropagation()"
     title="Otevřít v Apple Mail"
     style="text-decoration:none;font-size:13px;opacity:.5;line-height:1;display:inline-block;color:inherit;"
     onmouseover="this.style.opacity=1" onmouseout="this.style.opacity=.5">📧</a>
  {% else %}
  <span style="color:var(--text-dim);font-size:9px;">—</span>
  {% endif %}
</td>
<td style="white-space:nowrap;overflow:hidden">
  {% if m.typ %}<span class="typ-box {{ tc.get(m.typ, 'typ-info') }}">{{ m.typ }}</span>{% endif %}
  ...
```

## 5. EDGE CASES (povinně ošetřit)

| Situace | Chování |
|---|---|
| `source_id` v DB je `NULL` | `mail_url=None` → template zobrazí `—` v šedé barvě (`var(--text-dim)`) |
| `source_id` má kolem `< >` závorky | `build_mail_url()` je strippe |
| `source_id` obsahuje speciální znaky (`@`, `+`, `!`, mezery) | `urllib.parse.quote(mid, safe='')` zenkóduje vše |
| Klik na 📧 by mohl spustit zároveň `openEmailModal()` | `event.stopPropagation()` na anchoru — modal se NEOTEVŘE |
| `source_id` je prázdný string (whitespace) | `build_mail_url()` po `strip()` vrátí `None` |

## 6. TESTOVACÍ POSTUP (manual, pak commit)

### 6.1 Před deploy
1. ✅ V DB ověř, že sloupec `source_id` existuje a má data:
   ```bash
   docker exec brogi_postgres psql -U brogi -d assistance -c "
   SELECT COUNT(*) AS total,
          COUNT(source_id) AS with_id,
          COUNT(*) - COUNT(source_id) AS without_id
   FROM email_messages WHERE is_spam = FALSE;"
   ```
   Očekávaný výstup: `with_id` >> 0, `without_id` malé číslo (jen broken / forwarded emaily).

2. ✅ Sample 5 hodnot pro vizuální kontrolu (jestli mají závorky nebo ne):
   ```bash
   docker exec brogi_postgres psql -U brogi -d assistance -c "
   SELECT id, source_id FROM email_messages
   WHERE source_id IS NOT NULL AND is_spam = FALSE
   ORDER BY sent_at DESC LIMIT 5;"
   ```

### 6.2 Po deploy
1. **Build + restart dashboardu:**
   ```bash
   cd ~/SynologyDrive/001\ DXP/009\ BrogiASIST
   docker compose up -d --build dashboard
   docker logs brogi_dashboard --tail 30
   ```
2. **Otevřít `/` v prohlížeči** (lokálně `http://localhost:9000` nebo dle env).
3. **Vizuální kontrola:**
   - 📧 ikona je viditelná mezi *Předmět* a *Tagy* na každém řádku, který má `source_id`
   - U řádků bez `source_id` je šedý dash `—`
   - Hover na 📧 → opacity 1.0 (rozsvítí se)
4. **Funkční test (Apple Mail nainstalovaný):**
   - Klik na 📧 → otevře se Mail.app a vybere přesnou zprávu
   - Modal pro tagy se NEOTEVŘE (díky `stopPropagation`)
   - Test 5 různých emailů z různých účtů (icloud, gmail, forpsi, dxpsolutions, seznam)
5. **Test edge case** — najít email s `source_id IS NULL` a ověřit zobrazení `—`.
6. **Light + Dark theme** — přepnout v navu, ikona musí být viditelná v obou.

### 6.3 Co dělat když Mail.app nezareaguje
- Některé providery zapouzdřují Message-ID jinak (např. Gmail někdy přidává prefix). Pokud konkrétní email nereaguje:
  1. V Apple Mail otevři ten email manuálně → `View → Message → Raw Source` (⌘⌥U)
  2. Najdi řádek `Message-ID: <něco>`
  3. Porovnej s tím, co je v DB ve sloupci `source_id`
  4. Pokud se liší → ingest možná zachytává jen část. Logni do `docs/BUGS.md` jako BUG-XXX a pokračuj.
- **NE-debugovat to v rámci této feature** — feature je jen UI link, fix ingestu by byl jiný issue.

## 7. ROLLBACK

Pokud něco nefunguje, vrátit oba soubory přes `git checkout HEAD~1 -- services/dashboard/main.py services/dashboard/templates/index.html`. Žádné DB migrace, žádné změny v jiných službách → rollback je triviální.

## 8. OPEN QUESTIONS — ověřit před implementací

1. ⚠️ **Formát `source_id` v DB**: má závorky `<>` nebo bez? → ověřit `SELECT source_id FROM email_messages LIMIT 5;` (sekce 6.1 bod 2). `build_mail_url()` ošetřuje obě varianty, ale dobré vědět.
2. ⚠️ **Dashboard má bind mount?** → pokud NE, je nutný `docker compose up -d --build dashboard`. Pokud ANO, stačí `docker restart brogi_dashboard`. Viz `LESSONS-LEARNED v1` sekce 24.
3. 🐒 **Apple Mail spuštěný?** Ověřit, že na dev/prod stroji běží Apple Mail.app a má naindexované všechny účty — jinak `message://` link najde "(no matching messages)". To je out-of-scope této feature.

## 9. DEFINITION OF DONE

- [ ] `main.py` upraven dle sekce 4.1, `import urllib.parse` na vrcholu souboru
- [ ] `index.html` upraven dle sekce 4.2 (3 změny: colgroup, header, data row)
- [ ] Dashboard přebuildnutý, log čistý (žádný traceback)
- [ ] Vizuální kontrola provedena (sekce 6.2.3)
- [ ] Funkční test 5 emailů provedl Pavel a potvrdil OK
- [ ] Edge case `source_id IS NULL` ověřen (zobrazí `—`)
- [ ] Light + Dark theme ověřeno
- [ ] Změny commitnuty + tagged dle GLOBAL-SKILL.md sekce 10:
  ```bash
  cd ~/SynologyDrive/001\ DXP/009\ BrogiASIST
  git add services/dashboard/main.py services/dashboard/templates/index.html docs/feature-specs/FEATURE-EMAIL-MAIL-LINK-v1.md
  git commit -m "Email mail.app link na index — sloupec mezi Předmět/Tagy (FEATURE-EMAIL-MAIL-LINK-v1)"
  git push origin 2
  git tag -a v2026.04.30.0 -m "Email mail.app link"
  git push origin --tags
  ```
- [ ] Záznam do `docs/brogiasist-lessons-learned-v1.md` pokud cokoliv neočekávaného (např. pokud konkrétní provider neotvírá link)

## 10. POZNÁMKY

- 🍏 `message://` URL scheme je oficiální macOS feature (Apple Mail registruje handler).
- 🍏 Funguje **jen** s Apple Mail.app. Pavel pracuje na macOS → OK pro tento use case.
- 🍎 Pokud Pavel jednou v budoucnu otevře dashboard z mobilu/Linuxu, link nezareaguje. Out-of-scope.
- 🍏 `event.stopPropagation()` je nutný — řádek má `onclick="openEmailModal('{{ m.id }}')"` a bez toho by klik na 📧 zároveň otevřel tag-modal.

---
*Konec specifikace. Pokračuje implementace v Claude Code.*

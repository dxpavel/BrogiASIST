---
Název: Workflows BrogiMatAssistance
Soubor: docs/brogimat-assistance-workflows-v1.md
Verze: 3.0
Poslední aktualizace: 2026-04-07
Popis: Automatizace, triggery, vstupy/výstupy, rutiny, Mantis
Změněno v: Přidán Mantis monitoring modul
---

# Workflows — BrogiMatAssistance

---

## Aktuální stav
Webhook bridge postaven a otestován. n8n routing připraven (kód), nenastavený.
Mantis API ověřeno — 7 issues načteno přes REST API.

---

## Workflow 1 — *brogi routing (připraveno, nenastaveno)

Trigger: libovolný vstup do n8n (Telegram, web, tlačítko)
Podmínka: zpráva začíná *brogi
Akce: strip prefixu → POST na webhook → vrátit výsledek

## Workflow 2 — rutinní tlačítka (plán)

| Tlačítko | Task |
|---|---|
| Zkontroluj inbox | výpis OmniFocus inbox |
| Úkoly po termínu | overdue tasks z OmniFocus |
| Ranní briefing | OmniFocus + Mantis summary |
| Přidej úkol | nový úkol do OmniFocus |
| Mantis přehled | otevřené issues |

## Workflow 3 — Mantis monitoring (plán)

### Co API umí (ověřeno)
- GET /api/rest/issues — výpis issues s filtry
- GET /api/rest/issues/{id} — detail + komentáře
- POST /api/rest/issues — nový issue
- POST /api/rest/issues/{id}/notes — komentář
- PATCH /api/rest/issues/{id} — změna statusu, handlera

### Co bude Brogi hlídat
- Denní ráno: issues po termínu → Telegram notifikace
- Nové issues bez handlera → upozornění
- Issues assigned déle než 7 dní bez změny → eskalace
- Weekly summary: otevřeno/zavřeno/po termínu

### Implementace
Buď jako samostatný n8n workflow s Schedule triggerem (cron),
nebo jako součást ranního briefingu.
Rozhodnutí: necháno na Pavlovi až při designu.

## Workflow 4 — session paměť (plán do budoucna)

Stejný princip jako BrogiMAT v5 sessionID.
Každá konverzace sdílí kontext přes DB tabulky sessions + session_messages.
Webhook server sestaví historii jako kontext pro každý call.
Expiry: počet interakcí / timeout / Pavel zavře.
Detaily: viz brogimat-assistance-system-popis-v1.md

## Workflow 5 — email (plán)

Mailboxy konfigurovatelné přes DB tabulku mailboxes.
Sdílená struktura s budoucími projekty.
Mailboxy: brogi@dxpsolutions.cz (ověřeno), iCloud (TBD).

## Workflow 6 — iMessage (plán)

Plugin imessage existuje v Claude Code (neaktivní).
Aktivace: /plugin install imessage v Claude Code terminálu.
Messages app přihlášena na Apple ID na Mac Studiu — ready.

## Logy a historie

- Webhook log: /Users/dxpavel/brogi-webhook/server.log
- Claude Code session history: /Users/dxpavel/.claude/projects/-Users-dxpavel-brogi-webhook/
- Formát: JSONL (role, content, model, timestamp)

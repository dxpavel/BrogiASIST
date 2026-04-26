---
Název: API Reference BrogiMatAssistance
Soubor: docs/brogimat-assistance-api-reference-v1.md
Verze: 2.0
Poslední aktualizace: 2026-04-06
Popis: Endpointy webhook serveru, request/response, příklady
Změněno v: První implementace 2026-04-06
---

# API Reference — BrogiMatAssistance

## Webhook server
Base URL (LAN): `http://10.55.2.117:8765`
Base URL (budoucí PROD): `https://assistance.brogi.online`

---

## GET /health
Health check — bez autentizace.

**Response 200:**
```json
{ "status": "ok", "server": "brogi-webhook", "port": 8765 }
```

---

## POST /task
Hlavní endpoint — pošle task Claude Code na Mac Studiu.

**Headers:**
```
Content-Type: application/json
X-Brogi-Token: brogi-secret-2026
```

**Request body:**
```json
{ "task": "zkontroluj úkoly v OmniFocus inbox" }
```

**Response 200:**
```json
{
  "status": "ok",
  "task": "zkontroluj úkoly v OmniFocus inbox",
  "output": "1. Re: Santa Fe\n2. Zajistit pro Barču...",
  "timestamp": "2026-04-06T22:12:41.326563"
}
```

**Response 401 (špatný token):**
```json
{ "error": "unauthorized" }
```

**Response 500 (timeout):**
```json
{ "error": "timeout 120s" }
```

---

## Příklady tasků (ověřeno)

```bash
# OmniFocus inbox
curl -X POST http://10.55.2.117:8765/task \
  -H "Content-Type: application/json" \
  -H "X-Brogi-Token: brogi-secret-2026" \
  -d '{"task": "Use osascript to get first 5 incomplete tasks from OmniFocus inbox"}'

# Jednoduchý test
curl -X POST http://10.55.2.117:8765/task \
  -H "Content-Type: application/json" \
  -H "X-Brogi-Token: brogi-secret-2026" \
  -d '{"task": "reply with exactly: BROGI_OK"}'
```

## n8n konfigurace (HTTP Request node)
```
Method: POST
URL: http://10.55.2.117:8765/task
Headers:
  Content-Type: application/json
  X-Brogi-Token: brogi-secret-2026
Body (JSON):
  { "task": "{{ $json.task }}" }
Timeout: 130000ms
```

## n8n routing *brogi (Code node)
```javascript
const message = $input.first().json.message || "";
const hasBrogi = message.trim().toLowerCase().startsWith("*brogi");
if (hasBrogi) {
  const task = message.replace(/^\*brogi\s*/i, "").trim();
  return [{ json: { task, is_brogi: true } }];
} else {
  return [{ json: { message, is_brogi: false } }];
}
```

---

# Apple Bridge endpointy (Apple Studio :9100, branch `2` updated 2026-04-26)

Apple Bridge na PajaAppleStudio (10.55.2.117) — FastAPI proxy nad Apple JXA/AppleScript.

## GET `/health`
Vrátí `{"ok": true, "ts": "..."}`.

## OmniFocus

### GET `/omnifocus/tasks`
Vrátí `{ok, count, tasks: [{id, name, flagged, in_inbox, due_at, defer_at, modified_at, status}]}`.

### GET `/omnifocus/projects`
Seznam projektů s jejich stavy.

### POST `/omnifocus/add_task`
Body: `{name, note, flagged?, email_id?, files?: [{filename, content_base64, size_bytes}]}`.
Vrátí `{ok, name, attach_method?, attach_errors?}`.

### GET `/omnifocus/task/{task_id}` (NEW 2026-04-26)
Fetch konkrétního OF tasku. Response: `{ok, task: {id, name, note, completed, flagged, in_inbox, due_at, defer_at, modified_at}}` nebo `{ok: false, error}`.

### POST `/omnifocus/task/{task_id}/append_note` (NEW 2026-04-26)
Body: `{text, separator?}` — append k OF notes. Response: `{ok, task_id, new_length}`.

## Apple Notes

### GET `/notes/all`
Seznam Apple Notes notes.

### POST `/notes/add`
Body: `{name, body, folder?}`.

### GET `/notes/{note_id}` (NEW 2026-04-26)
Fetch konkrétní note. Response: `{ok, note: {id, name, body, creation_date, modification_date}}`.

### POST `/notes/{note_id}/append` (NEW 2026-04-26)
Body: `{text, separator?: true}` — HTML-safe append (escape `& < >`, `\n` → `<br/>`).

## Apple Contacts (JXA, NEW 2026-04-26)

### GET `/contacts/all`
Vrátí kontakty + jejich skupiny přes JXA `Application('Contacts')`.
Response: `{ok, count, contacts: [{id, first, last, org, modified_at, emails: [], phones: [], groups: [...]}]}`.

⚠️ Trvá ~100s pro 1180 kontaktů. Klient potřebuje timeout 240s+.

🍎 **BUG-009:** emails/phones zatím vynechané (per-property volání drahé) → fix po blockeru D5.

### GET `/contacts/all_sqlite` (legacy fallback)
Vyžaduje FDA — vrací `{ok: false, error: "no_fda"}` pokud Bridge nemá.

## Apple Reminders

### POST `/reminders/add`
Body: `{name, body?, due_date?}`.

### GET `/reminders/all`
Seznam reminders.

## Apple Calendar

### GET `/calendar/events?days=N`
Nadcházející události na N dní.

### POST `/calendar/add`
Body: `{title, start, end?, location?, notes?, calendar?}`.

⏳ TODO `/calendar/reply` — Accept/Decline reply pro pozvánku (BUG-010 — Mail.app neumí custom headers).

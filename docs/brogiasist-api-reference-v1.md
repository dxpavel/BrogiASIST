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

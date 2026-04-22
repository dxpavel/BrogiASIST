---
Název: Systémový popis BrogiMatAssistance
Soubor: docs/brogimat-assistance-system-popis-v1.md
Verze: 2.0
Poslední aktualizace: 2026-04-06
Popis: Co systém dělá, architektura, dataflow, lokální nástroje
Změněno v: První implementace 2026-04-06
---

# Systémový popis — BrogiMatAssistance

---

## Co systém dělá
Osobní asistent pro Pavla. Přebírá denní operativu:
- čtení a třídění emailů
- správa úkolů (OmniFocus, Reminders)
- odesílání zpráv (iMessage)
- rutiny a denní briefing
Pavel potvrzuje rozhodnutí, systém vykonává.

## Architektura

```
[Pavel — telefon / web]
        │
        ▼
  [n8n na Synology]
        │
   obsahuje *brogi?
   ┌────┴────┐
  ANO       NE
   │         └── normální n8n flow
   ▼
HTTP POST → http://10.55.2.117:8765/task
  header: X-Brogi-Token
  body: { "task": "přirozený jazyk" }
        │
        ▼
[Python webhook server — LaunchAgent — Mac Studio]
        │
        ▼
[Claude Code v2.1.92 — Max účet — Opus 4.6]
        │
   ┌────┼────┬────────┐
   ▼    ▼    ▼        ▼
OmniFocus Notes iMessage Soubory
(AppleScript) (MCP) (plugin) (filesystem)
        │
        ▼
JSON odpověď → n8n → Pavel
```

## Lokální nástroje na Mac Studiu

| Nástroj | Přístup | Stav |
|---|---|---|
| OmniFocus | AppleScript (osascript) | ✅ ověřeno |
| Apple Notes | MCP server (Read and Write Apple Notes) | ✅ připojen |
| Apple Reminders | AppleScript | ⏳ netestováno |
| Apple Mail | AppleScript | ⏳ netestováno |
| iMessage / SMS | Claude Code plugin (imessage) | ⏳ neaktivní |
| Soubory | filesystem přímý přístup | ✅ funguje |
| Docker | Bash (docker-compose) | ✅ povoleno |

## Billing model
| Kde | Platí se z |
|---|---|
| Claude Code webhook calls | Max předplatné (dxpavel@me.com) |
| n8n API calls (pokud volá Anthropic API přímo) | API kredity |
| Webhook server provoz | zdarma (lokální Python) |

Session history webhook calls se ukládá lokálně:
`/Users/dxpavel/.claude/projects/-Users-dxpavel-brogi-webhook/*.jsonl`
V claude.ai chat history se NEZOBRAZÍ.

## Bezpečnost
- Webhook server přístupný pouze z LAN (10.55.2.0/24)
- Autentizace: X-Brogi-Token header (viz credentials)
- Claude Code běží s --dangerously-skip-permissions
  (vědomé rozhodnutí — lokální stroj, LAN only)
- SSH přístup: key-only (id_ed25519 z MacBook Pro)

## Omezení
- Timeout Claude Code: 120s per task
- Max předplatné limity: reset každých 5 hodin
- LaunchAgent vyžaduje přihlášeného uživatele dxpavel
- Gmail / Google Calendar: potřebují re-auth, nevyužíváme
## Session paměť (plán do budoucna)

Stejný princip jako BrogiMAT v5 sessionID.

### Jak by fungovalo
Každá konverzace s Brogim má sessionID. Všechny tasky v rámci session
sdílejí kontext — Claude Code vidí historii předchozích odpovědí.

### Co by se muselo přidat
1. DB tabulka `sessions` — id, stav, created, expires, Pavel_potvrdil
2. DB tabulka `session_messages` — session_id, role, content, timestamp
3. Webhook server: přijímá volitelně `session_id`, načte historii z DB,
   přidá jako kontext do každého tasku

### Expiry (stejně jako v BrogiMAT v5)
- počet interakcí (např. max 20)
- timeout (např. 30 min bez aktivity)
- Pavel explicitně uzavře / klikne "hotovo"

### Příklad použití
Pavel: "zkontroluj maily a připrav odpovědi"
  → session ses_abc123 vznikne
  → call 1: čti inbox → vrátí seznam 5 mailů
  → call 2: "odpověz na mail č.3" → Claude vidí seznam z call 1
  → call 3: potvrzení odeslání
  → Pavel: "hotovo" → session uzavřena

### Poznámka
Pro jednorázové rutiny (zkontroluj inbox, přidej úkol) session není potřeba.
Session řeší až vícekrokové dialogy.

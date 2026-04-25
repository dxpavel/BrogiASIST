---
Název: Plán funkcí BrogiMatAssistance
Soubor: docs/brogimat-assistance-feature-plan-v1.md
Verze: 1.0
Poslední aktualizace: 2026-04-07
Popis: Kompletní seznam plánovaných funkcí před designem a implementací
---

# Plán funkcí — BrogiMatAssistance

Sestaveno před designem. Teprve až je seznam kompletní,
přejdeme na: DB schéma → WFL design → WebUI → implementace.

---

## MODUL 1 — Email

### Zdroje
- brogi@dxpsolutions.cz (IMAP/SMTP ověřeno ✅)
- iCloud (TBD — app-specific password)

### Funkce
- Čtení příchozích emailů
- Třídění do kategorií (klient / spam / marketing / interní)
- Scoring — kdo píše, jak často, trend
- Návrh odpovědi (Claude)
- Odeslání odpovědi po Pavlově potvrzení
- Analytika: % klientů vs ostatní, průměrná doba odpovědi, trendy

### DB
- PostgreSQL tabulka emails (datum, od, kategorie, délka, akce, odpověděno)
- Konfigurace mailboxů přes DB (sdílená s budoucími projekty)

### Vektorová paměť (addon)
- ChromaDB — sémantické vyhledávání "najdi emaily podobné této poptávce"
- pgvector jako alternativa (v PostgreSQL)

---

## MODUL 2 — SMS / iMessage

### Zdroje
- iMessage — plugin v Claude Code (existuje, neaktivní)
- SMS — přes Apple Messages (Mac Studio)

### Funkce
- Čtení příchozích zpráv
- Notifikace důležitých zpráv
- Odeslání zprávy po Pavlově potvrzení

---

## MODUL 3 — MantisBT

### Zdroj
- https://servicedesk.dxpavel.cz (API ověřeno ✅)
- API token: viz credentials

### Funkce
- Denní přehled otevřených issues
- Issues po termínu → Telegram notifikace
- Issues bez handlera → upozornění
- Issues assigned déle než 7 dní bez změny → eskalace
- Weekly summary: otevřeno / zavřeno / po termínu
- Vytvoření nového issue
- Přidání komentáře
- Změna statusu / handlera

---

## MODUL 4 — RSS monitoring

### Funkce
- Odběr RSS kanálů (konfigurace v DB)
- Filtrování novinek podle klíčových slov
- Denní nebo realtime digest
- Notifikace přes Telegram

### Poznámka
RSS je jednoduché HTTP polling — žádné speciální API.
n8n má nativní RSS node.

---

## MODUL 5 — YouTube monitoring

### Funkce
- Sledování kanálů (YouTube Data API nebo RSS feed kanálu)
- Notifikace nového videa
- Volitelně: shrnutí obsahu videa přes Claude

### Poznámka
YouTube kanály mají RSS feed:
https://www.youtube.com/feeds/videos.xml?channel_id=CHANNEL_ID
Lze řešit stejně jako RSS — bez API klíče.

---

## MODUL 6 — OmniFocus (hotovo ✅)

### Funkce (ověřeno)
- Výpis inbox úkolů
- Výpis úkolů po termínu
- Výpis úkolů projektu
- Přidání úkolu
- Ranní briefing

---

## MODUL 7 — Apple Notes

### Zdroj
- MCP server připojen ✅

### Funkce
- Čtení poznámek
- Vytvoření nové poznámky
- Vyhledávání v poznámkách

---

## MODUL 8 — Apple Reminders

### Funkce (plán, netestováno)
- Výpis připomínek
- Vytvoření připomínky
- Splnění připomínky

---

## MODUL 9 — Analytika a paměť

### Funkce
- PostgreSQL: statistiky emailů, akcí, trendů
- ChromaDB: vektorová paměť pro sémantické vyhledávání
- Session paměť: vícekrokové dialogy (viz system-popis)

---

## TECHNICKÁ ARCHITEKTURA (platí pro vše)

```
Pavel (Telegram / WebUI / tlačítko)
  ↓
n8n (Synology) — routing, scheduling, triggery
  ↓
Webhook bridge (Mac Studio :8765)
  ↓
Claude Code (Opus 4.6, Max)
  ↓
Lokální nástroje (OmniFocus, Notes, Messages, Mail...)
  ↓
Odpověď → n8n → Pavel
```

Doména: assistance.brogi.online (vzor: BrogiMAT v5)
VPN: WireGuard (Unifi)

---

## POŘADÍ IMPLEMENTACE (návrh)

| Priorita | Modul | Důvod |
|---|---|---|
| 1 | Email | Nejvíc času zabere denně |
| 2 | MantisBT | Ověřeno, jednoduché |
| 3 | RSS | Jednoduché, n8n nativní |
| 4 | YouTube | RSS feed, bez API |
| 5 | SMS/iMessage | Plugin existuje |
| 6 | Reminders | AppleScript |
| 7 | Analytika/DB | Závisí na datech z 1-6 |

---

## CO MUSÍ BÝT HOTOVÉ PŘED IMPLEMENTACÍ

- [ ] DB schéma (emaily, mailboxy, sessions, mantis log, RSS kanály)
- [ ] WebUI design (zelená — odlišení od 008)
- [ ] WFL struktura v n8n
- [ ] assistance.brogi.online doména
- [ ] iCloud app-specific password
- [ ] iMessage plugin aktivace

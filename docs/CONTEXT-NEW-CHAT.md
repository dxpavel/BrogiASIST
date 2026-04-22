---
Název: CONTEXT-NEW-CHAT
Soubor: docs/CONTEXT-NEW-CHAT.md
Verze: 3.0
Poslední aktualizace: 2026-04-07
Popis: Kontext pro nový chat — stav, cesty, problémy
Změněno v: Přidán Mantis, session paměť, aktualizace stavu
---

# CONTEXT-NEW-CHAT — BrogiMatAssistance

---

## Co projekt je
Osobní asistent pro Pavla — přebírá operativu (emaily, OmniFocus, iMessage,
Mantis, rutiny). Pavel potvrzuje rozhodnutí, asistent vykonává.
Cíl: z 1-2h operativy denně na 10-15 minut.

## Aktuální stav (2026-04-07)
- Co běží: Webhook bridge na Mac Studiu (port 8765, LaunchAgent), Claude Code v2.1.92
- Co se řeší: n8n routing *brogi, iMessage plugin, DB schéma emailů, Mantis monitoring
- Co je rozbité: —

## Klíčové cesty
- Root: /Users/pavel/SynologyDrive/001 DXP/009 BrogiMAT Assistance/
- Webhook server: /Users/dxpavel/brogi-webhook/ (Mac Studio)
- LaunchAgent: /Users/dxpavel/Library/LaunchAgents/com.brogimat.webhook.plist
- Dokumentace: <ROOT>/docs/
- Credentials: <ROOT>/docs/brogimat-assistance-credentials-v1.md

## Aktivní komponenty
| Komponenta | Stav | Kde běží |
|---|---|---|
| Claude Code v2.1.92 | ✅ běží | Mac Studio (dxpavel) |
| Webhook server Python | ✅ LaunchAgent | Mac Studio :8765 |
| IMAP brogi@dxpsolutions.cz | ✅ ověřeno | mail.dxpsolutions.cz |
| OmniFocus (AppleScript) | ✅ ověřeno | Mac Studio |
| Apple Notes (MCP) | ✅ připojen | Mac Studio |
| MantisBT API | ✅ ověřeno | servicedesk.dxpavel.cz |
| iMessage plugin | ⏳ neaktivní | Mac Studio |
| Apple Reminders | ⏳ netestováno | Mac Studio |
| n8n routing *brogi | ⏳ připraveno | Synology server |
| Mantis monitoring WFL | ⏳ plán | Synology server |

## DEV / PROD architektura
- DEV: MacBook Pro (10.55.2.73) — Claude Desktop + MCP
- PROD server: Mac Studio (10.55.2.117) — Claude Code + webhook
- Doména: assistance.brogi.online (připravit)
- VPN: WireGuard (Unifi)

## Otevřené problémy
- [ ] n8n routing *brogi — kód připraven, nenastaveno v n8n
- [ ] iMessage plugin — existuje, neaktivní
- [ ] Apple Reminders — netestováno
- [ ] DB schéma emailů — architektura navržena, neimplementováno
- [ ] assistance.brogi.online — doména nepřipojena
- [ ] Mantis monitoring WFL — plán, neimplementováno
- [ ] Session paměť — plán, neimplementováno

## Poslední rozhodnutí
| Datum | Rozhodnutí |
|---|---|
| 2026-04-06 | Projekt spuštěn — webhook bridge postaven a otestován |
| 2026-04-06 | *brogi = jedno kouzelné slovo (ne 2 úrovně zatím) |
| 2026-04-06 | Gmail vyřazen — nevyužívá se |
| 2026-04-06 | IMAP brogi@dxpsolutions.cz ověřen (LOGIN OK) |
| 2026-04-06 | OmniFocus přes AppleScript ověřen reálným výpisem |
| 2026-04-06 | Platba: webhook calls z Max předplatného |
| 2026-04-07 | MantisBT API ověřeno — 7 issues načteno |
| 2026-04-07 | Mantis auth: header bez Bearer (jen token přímo) |
| 2026-04-07 | Mantis monitoring = součást 009, detail WFL na Pavlovi |
| 2026-04-07 | Session paměť zdokumentována jako budoucí plán |

## Lessons learned
→ Viz docs/LESSONS-LEARNED.md

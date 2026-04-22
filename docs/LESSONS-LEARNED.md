---
Název: Lessons Learned BrogiMatAssistance
Soubor: docs/LESSONS-LEARNED.md
Verze: 2.0
Poslední aktualizace: 2026-04-06
Popis: Poučení z praxe
Změněno v: Session 2026-04-06 — první implementace
---

# Lessons Learned — BrogiMatAssistance

---

## Session 2026-04-06 — Webhook bridge a Claude Code

### L1 — Desktop Commander se připojuje na jiný stroj
Desktop Commander běží na MacBook Pro (10.55.2.73), ne Mac Studio.
Ověřit vždy: `hostname && ipconfig getifaddr en0` před prací.

### L2 — Claude Code potřebuje /etc/paths.d/node
LaunchAgent nemá přístup k loginshell PATH.
Node na Mac Studiu je v /usr/local/bin — bez /etc/paths.d/node
ho LaunchAgent nenajde. Fix: `echo "/usr/local/bin" | sudo tee /etc/paths.d/node`

### L3 — OAuth vs API klíč v Claude Code
Claude Code při instalaci nabídne OAuth (Max) nebo API klíč.
Pokud je nastavena proměnná ANTHROPIC_API_KEY, vznikne konflikt.
Fix: `/logout` → přihlásit se znovu pouze přes OAuth (Max).
Ověření: musí zobrazit `Claude Max` ne `API Usage Billing`.

### L4 — Xcode licence blokuje Python3
Na čistém Macu Python3 odmítne běžet dokud není akceptována Xcode licence.
Fix: `sudo xcodebuild -license accept`

### L5 — LaunchAgent vs nohup konflikty
Pokud nohup process drží port a LaunchAgent se snaží nastartovat,
LaunchAgent crashuje do loopu (vidět v server.err jako Address already in use).
Fix: `pkill -9 -f "server.py"` pak LaunchAgent nastartuje sám.

### L6 — -p mode neukládá do claude.ai history
Claude Code s `-p` (print/neinteraktivní) flag ukládá sessiony lokálně
do JSONL ale NEzobrazuje se v claude.ai webovém rozhraní.
To je OK — máme vlastní log v server.log.

### L7 — OmniFocus funguje bez MCP přes AppleScript
Žádný OmniFocus MCP neexistuje. Claude Code ho ovládá přes
`osascript` přímo — spolehlivé, ověřeno reálným výpisem.

### L8 — SSH klíč musí být přidán do authorized_keys na Mac Studiu
Remote Login (SSH) musí být zapnut v System Settings → Sharing.
Klíč MacBook Pro (id_ed25519) přidán do /Users/dxpavel/.ssh/authorized_keys.

### L9 — Webhook server musí mít CLAUDE.md kontext
Bez CLAUDE.md Claude Code neví co je Brogi Mat.
CLAUDE.md musí být ve složce kde se spouští Claude Code (run-claude.sh dělá cd).

### L10 — Billing: Max vs API kredity
Webhook calls přes OAuth (Max) = z Max předplatného.
Pokud je přihlášen přes API klíč = z API kreditů.
Ověřit: `claude /status` musí zobrazit `Claude Max`.

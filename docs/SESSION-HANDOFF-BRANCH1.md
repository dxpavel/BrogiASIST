# BrogiASIST — Handoff prompt pro novou session
# Větev: 1 | Úkol: přenos příloh emailů do OmniFocus

---

## KROK 1 — PŘEČTI NEJDŘÍV (povinné)

Přečti tyto dokumenty než cokoliv uděláš:

```
/Users/pavel/SynologyDrive/001 DXP/009 BrogiASIST/docs/brogiasist-architecture-v1.md
/Users/pavel/SynologyDrive/001 DXP/009 BrogiASIST/docs/brogiasist-data-dictionary-v1.md
/Users/pavel/SynologyDrive/001 DXP/009 BrogiASIST/docs/brogiasist-lessons-learned-v1.md
/Users/pavel/SynologyDrive/001 DXP/009 BrogiASIST/docs/brogiasist-infrastructure-v1.md
```

---

## KROK 2 — KOMUNIKAČNÍ PRAVIDLA (absolutní)

Pavel má Asperger + ADHD. Tato pravidla jsou povinná vždy:

- **Strukturovaně, bez omáčky a keců**
- **Jedna otázka najednou** — nikdy víc
- **Nejdřív se zeptej, pak implementuj** — nikdy nerozhoduj sám
- **Nikdy se nevrhej na implementaci bez odsouhlasení** — ani když si myslíš že víš
- **Označovat**: 🍏 ok/hotovo | 🍎 problém | 🐒 riziko | ⚠️ varování
- **Před UI/architekturou**: navrhni → počkej na souhlas → pak dělej
- **Před prací**: vždy přečti zdrojový kód, nikdy nepředpokládej co tam je

---

## KROK 3 — TVŮJ JEDINÝ ÚKOL V TÉTO SESSION

**Implementovat přenos příloh emailů přes base64 do OmniFocus (a případně Notes).**

Jsme na git větvi `1`. Na této větvi pracuj.

### Kontext

Aktuální stav (DEV, funguje částečně):
- Scheduler ukládá přílohy emailů na disk: `/app/attachments/<uuid>/<filename>`
- Bind mount: `/Users/pavel/Desktop/OmniFocus:/app/attachments`
- Při OF akci: `telegram_callback.py` předává `file_paths` (lokální cesty) na Apple Bridge
- Apple Bridge čte soubory z těchto cest a pokouší se je připojit do OF

Problém:
- `NSFileWrapper` attach v OmniFocus přes JXA je nespolehlivý
- Na PRODu scheduler (BrogiServer) a Apple Bridge (Apple Studio) jsou na jiných strojích → sdílené cesty nefungují

### Navrhované řešení (odsouhlaseno Pavlem)

Místo lokálních cest posílat obsah souboru jako **base64 přímo v API callu**:

```
scheduler čte soubor → base64 → POST /omnifocus/add_task {files: [{filename, content_base64}]}
Apple Bridge → decode → uloží ~/Desktop/BrogiAssist/<uuid>/ → file:// link v OF note
```

Funguje stejně na DEV i PROD bez sdíleného filesystemu.

### Soubory ke změně

1. `services/ingest/telegram_callback.py` — OF action: čtení souboru + base64 encode
2. `services/apple-bridge/main.py` — endpoint `/omnifocus/add_task`: decode + uložit + link
3. `sql/011_claude_sender_verdicts.sql` — chybějící SQL migrace (vytvořit)

### Postup

1. Přečti aktuální kód obou souborů
2. Navrhni změny (neimplementuj)
3. Počkej na souhlas
4. Implementuj
5. Odzkoušej na DEV

---

## PŘÍSTUPY A PROSTŘEDÍ

```bash
# DEV kontejnery (běží lokálně)
docker logs brogi_scheduler --tail 20
docker exec brogi_scheduler python3 -c "..."

# Apple Bridge (Mac host, port 9100)
curl http://localhost:9100/health

# SSH PROD (až na to přijde čas — NE v této session)
ssh forpsi-root        # BrogiServer
ssh dxpavel@10.55.2.117  # PajaAppleStudio
```

---

## CO NEDĚLAT V TÉTO SESSION

- ❌ Neřeš PROD migraci
- ❌ Neinstaluj nic na BrogiServer ani Apple Studio
- ❌ Nezakládej nové větve
- ❌ Nerozhoduj o architektuře bez odsouhlasení

---

*Větev 1 vytvořena 2026-04-26 z 0.1.0.*
*Po otestování příloh na DEV → nová session pro PROD migraci.*

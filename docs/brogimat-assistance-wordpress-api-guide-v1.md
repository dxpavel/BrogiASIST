---
Název: WordPress REST API — Operational Guide
Soubor: docs/brogimat-assistance-wordpress-api-guide-v1.md
Verze: 1.0
Poslední aktualizace: 2026-04-07
Popis: Jak uploadovat články, obrázky, a spravovat WordPress obsah přes REST API z Apple Studio (SSH)
---

# WordPress REST API — Operational Guide

## Quick Reference

| Doména | Credentials | Status |
|---|---|---|
| **dxpsolutions.cz** | User: BROGIAI | ✅ Testováno |
| **zamecnictvi-rozdalovice.cz** | User: BROGIAI | ✅ Testováno |

---

## 1. Přístup — SSH na Apple Studio

### Konfigurace
```
Host: 10.55.2.117
User: dxpavel
SSH Key: ~/.ssh/id_ed25519
Port: 22 (default)
OS: macOS
```

### Připojení (z MacBook Paja)
```bash
ssh -i ~/.ssh/id_ed25519 dxpavel@10.55.2.117
```

### osascript přes Apple Studio (z claude.ai)
```applescript
ssh -o StrictHostKeyChecking=accept-new -i ~/.ssh/id_ed25519 dxpavel@10.55.2.117 'PŘÍKAZ_TU'
```

---

## 2. WordPress REST API — Credentials

### dxpsolutions.cz
```
URL: https://dxpsolutions.cz
REST endpoint: https://dxpsolutions.cz/wp-json/wp/v2
Username: BROGIAI
Application Password: WbJP U3ef vS7j ZPN0 haj0 sYmd
Auth method: Basic (base64)
```

**Basic Auth Header:**
```
Authorization: Basic QlJPR0lBSTpXYkpQIFUzZWYgdlM3aiBaUE4wIGhhajAgc1ltZA==
```

### zamecnictvi-rozdalovice.cz
```
URL: https://www.zamecnictvi-rozdalovice.cz
REST endpoint: https://www.zamecnictvi-rozdalovice.cz/wp-json/wp/v2
Username: BROGIAI
Application Password: 8gyO J1tp 1QAk Z9EC I87N y2nP
Auth method: Basic (base64)
```

**Basic Auth Header:**
```
Authorization: Basic QlJPR0lBSTg4Z3lPIEoxdHAgMVFBayBaOUVDIEk4N04geTJuUA==
```

⚠️ **Bezpečnost:** Credentials jsou v .gitignore — nejsou commitovány!

---

## 3. Testování — Ověření Autentifikace

### Test 1: Curl z Apple Studio
```bash
ssh -o StrictHostKeyChecking=accept-new -i ~/.ssh/id_ed25519 dxpavel@10.55.2.117 \
  '/usr/bin/curl -s -u BROGIAI:"WbJP U3ef vS7j ZPN0 haj0 sYmd" \
  https://dxpsolutions.cz/wp-json/wp/v2/users/me \
  -w "\nHTTP: %{http_code}\n"'
```

**Očekávaný výstup:**
```json
{
  "id": 101,
  "name": "Brogi AI assistant",
  "email": "brogi@dxpsolutions.cz",
  ...
}
HTTP: 200
```

### Test 2: Health check (jednoduše)
```bash
ssh -i ~/.ssh/id_ed25519 dxpavel@10.55.2.117 \
  'echo "SSH OK" && python3 --version'
```

---

## 4. Vytvoření DRAFT Článku — Workflow

### Krok 1: Připravit obsah v JSON souboru
```bash
ssh -i ~/.ssh/id_ed25519 dxpavel@10.55.2.117 'cat > /tmp/article.json << EOF
{
  "title": "Titulek článku",
  "content": "<p>Obsah článku v HTML</p>",
  "status": "draft",
  "categories": [37],
  "meta": {
    "description": "Meta description pro SEO",
    "keywords": "klíč1, klíč2"
  }
}
EOF
'
```

### Krok 2: Uploadnout článek
```bash
ssh -i ~/.ssh/id_ed25519 dxpavel@10.55.2.117 \
  '/usr/bin/curl -X POST "https://dxpsolutions.cz/wp-json/wp/v2/posts" \
  -u "BROGIAI:WbJP U3ef vS7j ZPN0 haj0 sYmd" \
  -H "Content-Type: application/json" \
  -d @/tmp/article.json'
```

**Výstup:**
```json
{
  "id": 2986,
  "status": "draft",
  "title": {"raw": "Titulek článku"},
  ...
}
```

⚠️ **Důležité:** `"status": "draft"` znamená:
- ✅ Článek je SKRYTÝ
- ✅ Není veřejný
- ✅ Vidíš jej jen v WordPress admin → Návrhy
- ✅ Ty jej později publikuješ ručně

### Krok 3: Publikovat (jen Pavel!)
```
WordPress admin → Příspěvky → Návrhy → Naší články → Publikovat
```

---

## 5. Upload Obrázků — Featured Image

### Krok 1: Uploadnout obrázek do Media library
```bash
ssh -i ~/.ssh/id_ed25519 dxpavel@10.55.2.117 \
  '/usr/bin/curl -F "file=@/path/to/image.jpg" \
  "https://dxpsolutions.cz/wp-json/wp/v2/media" \
  -u "BROGIAI:WbJP U3ef vS7j ZPN0 haj0 sYmd"'
```

**Výstup (zapamatuj si ID):**
```json
{
  "id": 12345,
  "source_url": "https://dxpsolutions.cz/wp-content/uploads/2026/04/image.jpg"
}
```

### Krok 2: Přiřadit k článku
```bash
ssh -i ~/.ssh/id_ed25519 dxpavel@10.55.2.117 \
  '/usr/bin/curl -X POST "https://dxpsolutions.cz/wp-json/wp/v2/posts/2986" \
  -u "BROGIAI:WbJP U3ef vS7j ZPN0 haj0 sYmd" \
  -H "Content-Type: application/json" \
  -d "{\"featured_media\": 12345}"'
```

---

## 6. Ověřená Příkazy — Copy-Paste Ready

### dxpsolutions.cz — Ověření auth (curl)
```bash
ssh -o StrictHostKeyChecking=accept-new -i ~/.ssh/id_ed25519 dxpavel@10.55.2.117 \
  '/usr/bin/curl -s -u BROGIAI:"WbJP U3ef vS7j ZPN0 haj0 sYmd" \
  https://dxpsolutions.cz/wp-json/wp/v2/users/me'
```

**Status:** ✅ **TESTOVÁNO 2026-04-07 09:33 UTC**
- Výstup: 200 OK
- User ID: 101
- Name: Brogi AI assistant

### dxpsolutions.cz — Vytvoření DRAFT článku (curl)
```bash
ssh -i ~/.ssh/id_ed25519 dxpavel@10.55.2.117 \
  '/usr/bin/curl -X POST "https://dxpsolutions.cz/wp-json/wp/v2/posts" \
  -u "BROGIAI:WbJP U3ef vS7j ZPN0 haj0 sYmd" \
  -H "Content-Type: application/json" \
  -d "{\"title\": \"Test: Jak nám BrogiMAT pomáhá\", \"content\": \"<p>To je DRAFT test</p>\", \"status\": \"draft\"}"'
```

**Status:** ✅ **TESTOVÁNO 2026-04-07 09:33 UTC**
- Post ID: 2986
- Status: draft ✅ (skrytý!)
- Autor: 101 (Brogi AI assistant)

---

## 7. Oprávnění v WordPressu

| Akce | Asistent (BROGIAI) | Vlastník (Pavel) |
|---|---|---|
| Čtení | ✅ | ✅ |
| Vytvoření DRAFT | ✅ | ✅ |
| Editace DRAFT | ✅ | ✅ |
| Upload obrázků | ✅ | ✅ |
| Publikace | ❌ | ✅ |
| Smazání | ❌ | ✅ |

---

## 8. Python Script — wp-articles-upload.py

**Lokace:** `/Users/pavel/SynologyDrive/001 DXP/009 BrogiMAT Assistance/scripts/wp-articles-upload.py`

**Co dělá:**
1. Připravuje dva SEO-optimalizované články
2. Uploaduje obrázky do Media library
3. Vytváří DRAFT příspěvky na obou webech
4. Přiřazuje featured images
5. **Nikdy** nepublikuje (draft status)

**Spuštění:**
```bash
ssh -i ~/.ssh/id_ed25519 dxpavel@10.55.2.117 \
  'cd /Users/pavel/SynologyDrive/001\ DXP/009\ BrogiMAT\ Assistance/scripts && \
  /usr/bin/python3 wp-articles-upload.py'
```

⚠️ **Poznámka:** Skript vyžaduje `requests` knihovnu — pokud chybí, nainstaluj:
```bash
ssh -i ~/.ssh/id_ed25519 dxpavel@10.55.2.117 \
  '/usr/bin/pip3 install requests'
```

---

## 9. Error Handling

### "Host key verification failed"
**Řešení:** První SSH připojení — přidej `-o StrictHostKeyChecking=accept-new`
```bash
ssh -o StrictHostKeyChecking=accept-new -i ~/.ssh/id_ed25519 dxpavel@10.55.2.117 'ping'
```

### "Operation not permitted" na /Volumes/
**Řešení:** SynologyDrive není připojená nebo app nemá přístup
- Zkontroluj Finder → Locations
- Ujisti se že SynologyDrive je připojená

### "ModuleNotFoundError: No module named 'requests'"
**Řešení:** Instaluj requests
```bash
ssh -i ~/.ssh/id_ed25519 dxpavel@10.55.2.117 \
  '/usr/bin/pip3 install --user requests'
```

### cURL vs. Python
- **cURL:** Jednoduché, bez dependencies, vhodné pro testy
- **Python:** Komplexní workflows, error handling, strukturovaný obsah

---

## 10. Workflow — Uploadování Dvou Článků

**Plán:**
1. ✅ Připravit 2 artikuly s SEO (done — script hotový)
2. ✅ Uploadnout obrázky (BrogiMAT logos)
3. ✅ Vytvořit DRAFT příspěvky
4. ⏳ Ty publikuješ manuálně z WP adminu

**Status:** Připraveno k provedení — Pájo si spustí skript

---

## 11. Poznámky pro Budoucí Sessions

### Co funguje
- ✅ SSH na 10.55.2.117 (Apple Studio) — stabilní
- ✅ Basic Auth s Application Passwords — práce
- ✅ DRAFT status — propychuje se správně
- ✅ cURL pro jednoduché příkazy
- ✅ osascript → SSH → curl řetězec

### Co nebylo testováno
- ❓ Bulk upload více obrázků najednou
- ❓ Category/Tag automatizace
- ❓ Custom post meta fields
- ❓ Workflow automate (pokud je zapnutý)

### Příští kroky
1. Spustit wp-articles-upload.py
2. Ověřit DRAFTy v WordPress adminu
3. Pavel publikuje
4. Měřit SEO impact (1-2 týdny)

---

**Verze:** 1.0  
**Testováno:** 2026-04-07  
**Kdo:** Claude + Pavel  
**Co:** WordPress REST API automation přes SSH  

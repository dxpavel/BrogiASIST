---
# PRE-TEST CHECKLIST
# 2026-04-07
# Než spustíme wp-articles-upload.py, zkontrolujeme tohle
---

## CHECKLIST — Ověření Podmínek

### 1️⃣ HTTPS + REST API dostupné

```bash
# Test 1: Jsou weby dostupné na HTTPS?
curl -I https://dxpsolutions.cz/wp-json/wp/v2/posts
curl -I https://www.zamecnictvi-rozdalovice.cz/wp-json/wp/v2/posts

# Očekávám: HTTP/2 200 nebo HTTP/1.1 200 (ne 404, ne DNS error)
```

✅ **Pokud OK:** HTTP 200 — REST API je dostupný  
❌ **Pokud FAIL:** HTTP 404 — REST API je vypnuté (musíme to zapnout)

---

### 2️⃣ BASIC AUTH — Credentials Fungují

```bash
# Test 2: dxpsolutions.cz
curl -u "BROGIAI:WbJP U3ef vS7j ZPN0 haj0 sYmd" \
  https://dxpsolutions.cz/wp-json/wp/v2/users/me

# Test 3: zamecnictvi-rozdalovice.cz
curl -u "BROGIAI:8gyO J1tp 1QAk Z9EC I87N y2nP" \
  https://www.zamecnictvi-rozdalovice.cz/wp-json/wp/v2/users/me
```

✅ **Pokud OK:** 
```json
{
  "id": 101,
  "name": "Brogi AI assistant",
  "email": "..."
}
```

❌ **Pokud FAIL — 401 Unauthorized:**
- Zkontroluj username case (BROGIAI, ne brogiai)
- Zkontroluj heslo — zkopiuj bez chyby z credentials

❌ **Pokud FAIL — 403 Forbidden:**
- User nemá roli nebo capability
- Zkontroluj v WordPress admin

---

### 3️⃣ DRAFT POST CREATION — Základní Test

```bash
# Test 4: dxpsolutions.cz — vytvoř draft
curl -X POST \
  -u "BROGIAI:WbJP U3ef vS7j ZPN0 haj0 sYmd" \
  -H "Content-Type: application/json" \
  -d '{"title":"TEST-DRAFT-123","content":"Test obsah","status":"draft"}' \
  https://dxpsolutions.cz/wp-json/wp/v2/posts
```

✅ **Pokud OK:**
```json
{
  "id": 9999,
  "status": "draft",
  "title": {"raw": "TEST-DRAFT-123"}
}
```

❌ **Pokud FAIL — 400 Bad Request:**
- JSON syntax chyba — zkontroluj escaping

❌ **Pokud FAIL — 403 Forbidden:**
- Context chyba? Zkus s `?context=edit`
- Role chyba? User nemá edit_posts capability

---

### 4️⃣ DRAFT VISIBILITY — Check `context=edit`

```bash
# Test 5: Můžeš číst draft s context=edit?
curl -u "BROGIAI:WbJP U3ef vS7j ZPN0 haj0 sYmd" \
  "https://dxpsolutions.cz/wp-json/wp/v2/posts/9999?context=edit"

# Test 6: Bez context=edit? (mělo by vrátit 403)
curl "https://dxpsolutions.cz/wp-json/wp/v2/posts/9999"
```

✅ **Pokud OK:**
- s `context=edit` → vidíš draft
- bez toho → 403 nebo nic (expected)

---

### 5️⃣ SECURITY PLUGIN CHECK — Je /wp-json/ Whitelisted?

```bash
# Test 7: Když je security plugin blokuje, dostaneš 410 Gone
curl -I https://dxpsolutions.cz/wp-json/wp/v2/posts

# Pokud je blokované:
# Jdi do WordPress admin → Security plugin settings
# Whitelist: /wp-json/*
```

✅ **Pokud OK:** HTTP 200  
⚠️ **Pokud 410 Gone:** Musíme whitelist v security pluginu

---

### 6️⃣ CACHING CHECK — Je /wp-json/ Vyklučeno?

```bash
# Test 8: Zapamatuj si response
curl -s https://dxpsolutions.cz/wp-json/wp/v2/posts?per_page=1 > /tmp/cache-test-1.json

# Počkej 5 minut
sleep 300

# Zapamatuj si znovu
curl -s https://dxpsolutions.cz/wp-json/wp/v2/posts?per_page=1 > /tmp/cache-test-2.json

# Jsou identické? (pokud ano = je cachované)
diff /tmp/cache-test-1.json /tmp/cache-test-2.json
```

✅ **Pokud RŮZNÉ:** Není cachované → OK  
⚠️ **Pokud STEJNÉ:** Může být cached → musíme to vyřešit

---

### 7️⃣ SSH na Apple Studio — Connectivity

```bash
# Test 9: Máš SSH přístup?
ssh -o StrictHostKeyChecking=accept-new -i ~/.ssh/id_ed25519 dxpavel@10.55.2.117 'echo "SSH OK"'
```

✅ **Pokud OK:** `SSH OK`  
❌ **Pokud FAIL:** SSH key problém — zkontroluj ~/.ssh/id_ed25519

---

### 8️⃣ PYTHON ENVIRONMENT — Jsou Dependencies?

```bash
# Test 10: Curl je k dispozici?
ssh -i ~/.ssh/id_ed25519 dxpavel@10.55.2.117 'which curl'

# Test 11: Python3?
ssh -i ~/.ssh/id_ed25519 dxpavel@10.55.2.117 'python3 --version'

# Test 12: Request modul (pokud script to vyžaduje)
ssh -i ~/.ssh/id_ed25519 dxpavel@10.55.2.117 'python3 -c "import requests"'
```

✅ **Pokud OK:** Všechny dostupné  
⚠️ **Pokud FAIL requests:** Je OK — máme curl alternativu

---

## SUMMARY — Status Před Startem

| Test | Status | Akce |
|------|--------|------|
| REST API dostupný | ✅/❌ | Pokud ❌: Enable REST API |
| Basic Auth funguje | ✅/❌ | Pokud ❌: Zkontroluj credentials |
| Draft post create | ✅/❌ | Pokud ❌: Zkontroluj JSON |
| Draft visibility | ✅/❌ | Pokud ❌: Přidej context=edit |
| Security plugin | ✅/⚠️ | Pokud ⚠️: Whitelist /wp-json/ |
| Caching | ✅/⚠️ | Pokud ⚠️: Vykluč /wp-json/ |
| SSH connectivity | ✅/❌ | Pokud ❌: Zkontroluj key |
| Python + curl | ✅/⚠️ | Pokud ⚠️: Instaluj |

---

## KDYŽ JE VŠE ✅

**Spusť test:**
```bash
ssh -i ~/.ssh/id_ed25519 dxpavel@10.55.2.117 \
  'cd /Users/pavel/SynologyDrive/001\ DXP/009\ BrogiMAT\ Assistance/scripts && \
  python3 wp-articles-upload.py 2>&1 | tee /tmp/upload-test.log'
```

**Monitoruj output:**
- First run: Upload image + create draft
- Second run: Check status
- Log file: `/tmp/upload-test.log`

---

## FAIL — Co Dělat

**Pokud se něco pokazí:**

1. **Archivuj error log:**
   ```bash
   ssh -i ~/.ssh/id_ed25519 dxpavel@10.55.2.117 'cat /tmp/upload-test.log'
   ```

2. **Zjisti error:**
   ```bash
   grep -i "error\|fail\|403\|401\|500" /tmp/upload-test.log
   ```

3. **Vrať se do pitfalls dokumentu:**
   - docs/brogimat-wordpress-api-pitfalls-v1.md
   - Shoduj error s top pitfalls (tabulka)

4. **Řeš jeden po jednom:**
   - Draft 403? → Přidej context=edit
   - Auth fail? → Zkontroluj credentials
   - Plugin blokuje? → Whitelist /wp-json/

---

**Čas:** ~15 minut na všechny testy  
**Těžkost:** Low (copy-paste curl příkazy)  
**Riziko:** Žádné (jen čteš/testuješ, nic neměníš)

✅ **Když je vše ✅ → Spustíme wp-articles-upload.py**

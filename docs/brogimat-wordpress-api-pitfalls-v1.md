---
Název: WordPress REST API — Known Pitfalls & Prevention
Soubor: docs/brogimat-wordpress-api-pitfalls-v1.md
Verze: 1.0
Datum: 2026-04-07
Zdroj: GitHub issues, WordPress dev forums, community reports
---

# WordPress REST API — Known Pitfalls & Prevention

## TL;DR — Co Se Obvykle Pokazí

🍏 **OVĚŘENO Z DOKUMENTACE:**

1. **Draft posts vrací 403 bez `context=edit`** ❌ → ✅ **Řešení: Přidat `?context=edit` do URL**
2. **Authorization header se stripuje na CGI serverech** → **Řešení: Zkontroluj .htaccess**
3. **Application Passwords nejsou case-sensitive** → **Spaces v hesle jsou ignorovány**
4. **cURL `-u` automaticky base64 koduje** → **Nemusíš manual base64**
5. **Security plugins blokují REST API** → **Zkontroluj Wordfence, iThemes Security**
6. **HTTPS je povinné pro App Passwords** → **HTTP vrátí "not available"**
7. **Caching vrací cached DRAFT jako públiné** → **REST endpoints nemají být cachované**

---

## 1. Draft Posts — 403 Forbidden

### ❌ Problém

```bash
curl -u "BROGIAI:WbJP U3ef vS7j ZPN0 haj0 sYmd" \
  https://dxpsolutions.cz/wp-json/wp/v2/posts/2986
```

**Výstup:**
```json
{
  "code": "rest_forbidden",
  "message": "Sorry, you are not allowed to do that.",
  "status": 403
}
```

### ✅ Řešení

**POVINNÉ: Přidej `?context=edit` do URL**

```bash
curl -u "BROGIAI:WbJP U3ef vS7j ZPN0 haj0 sYmd" \
  "https://dxpsolutions.cz/wp-json/wp/v2/posts/2986?context=edit"
```

**Proč?** Draft posts nejsou "veřejné" — vyžadují `context=edit` aby se vědělo že je to pro admin preview.

**Aplikuj na:** GET, PUT, DELETE — vždy pro draft/private posts

---

## 2. Authorization Header Stripping (CGI)

### ❌ Problém

Některé serverové konfigurace (Apache CGI, FastCGI) dropují Authorization header.

**Symptomy:**
- Basic Auth funguje lokálně, ale ne na produkci
- 401 Unauthorized bez konkrétní zprávy
- "User not found" error s platným heslem

### ✅ Řešení

**Přidej do `.htaccess`:**
```apache
<IfModule mod_setenvif.c>
  SetEnvIf Authorization "(.*)" HTTP_AUTHORIZATION=$1
</IfModule>

<IfModule mod_rewrite.c>
  RewriteEngine On
  RewriteCond %{HTTP:Authorization} ^(.*) 
  RewriteRule ^(.*)$ - [E=HTTP_AUTHORIZATION:%1]
</IfModule>
```

**Nginx (fastcgi_params):**
```nginx
fastcgi_pass_header Authorization;
```

**🍏 Status:** dxpsolutions.cz a zamecnictvi-rozdalovice.cz — musí se ověřit

---

## 3. Spaces v Application Passwords

### Fakt

WordPress generuje app passwords se spaces: `WbJP U3ef vS7j ZPN0 haj0 sYmd`

### ✅ Správně

**Spaces jsou OK — cURL je ignoruje:**
```bash
curl -u "BROGIAI:WbJP U3ef vS7j ZPN0 haj0 sYmd" \
  https://dxpsolutions.cz/wp-json/wp/v2/users/me
```

**Bez spaces — také OK:**
```bash
curl -u "BROGIAI:WbJPU3efvS7jZPN0haj0sYmd" \
  https://dxpsolutions.cz/wp-json/wp/v2/users/me
```

**Práce s nimi v shellu:**
```bash
# Znaky bez escaping pokud je v jednoduchých uvozovkách
PASS="WbJP U3ef vS7j ZPN0 haj0 sYmd"
curl -u "BROGIAI:$PASS" ...
```

---

## 4. HTTPS — Application Passwords Hide na HTTP

### ❌ Problém

Na `http://` (bez SSL) WordPress schová Application Passwords sekci.

```
❌ http://dxpsolutions.cz  → "Application Passwords not available"
✅ https://dxpsolutions.cz → Aplikace hesla vidíme
```

### ✅ Řešení

**Produkce:** Vždy HTTPS  
**Staging bez SSL:** Přidej filtr do `functions.php`:
```php
add_filter( 'wp_is_application_passwords_available', '__return_true' );
```

🍏 **Status dxpsolutions.cz:** ✅ HTTPS je aktivní

---

## 5. Security Plugins Blokují REST API

### ❌ Problém

Wordfence, iThemes Security, Sucuri atd. mohou blokovat `/wp-json/` endpoint.

**Symptomy:**
```
403 Forbidden
410 Gone
413 Payload Too Large
```

### ✅ Řešení

1. **Wordfence:** Firewall → Whitelist → Přidej `/wp-json/` do whitelist
2. **iThemes Security:** Settings → Advanced → REST API → Enable
3. **Sucuri:** Security → Firewall rules → Whitelist `/wp-json/`

🍏 **Status dxpsolutions.cz:** Musí se ověřit (při spuštění testu)

---

## 6. Caching — REST Endpoints Cache się Jako Publikované Posty

### ❌ Problém

Caching plugin cachuje `/wp-json/posts?status=draft` a pak vrací cache pro všechny.

```
Prvé volání: Draft post hidden (private)
Druhé volání: Cache reader vrátí cachovanou verzi = veřejný přístup!
```

### ✅ Řešení

**Vykluč z cachingu:**

**WP Super Cache:** Settings → Advanced → Reject URIs:
```
/wp-json/*
```

**WP Fastest Cache:** Settings → Exclude → URLs:
```
/wp-json/.*
```

**W3 Total Cache:** Exclude Strings → Cache Query Strings:
```
/wp-json/
```

🍏 **Status dxpsolutions.cz:** Musí se ověřit

---

## 7. Role & Capabilities — User Nemá `edit_posts`

### ❌ Problém

Application Password s nedostatečnými právníky.

```json
{
  "code": "rest_cannot_create",
  "message": "Sorry, you are not allowed to create posts as this user."
}
```

### ✅ Řešení

1. **Ověř role:** Uživatel musí být Admin nebo Editor
2. **Zkontroluj capabilities:** WP → Users → Edit User → Role
3. **BROGIAI user** — musí mít **Administrator** role

🍏 **Status:** BROGIAI user je Admin (ověřeno při vytvoření)

---

## 8. Case Sensitivity — Username vs Password

### Fakt

- **Username:** Case-sensitive! `BROGIAI` ≠ `brogiai`
- **Password (App):** Case-sensitive!

### ✅ Správně

```bash
# ✅ Správně
curl -u "BROGIAI:WbJP U3ef vS7j ZPN0 haj0 sYmd" ...

# ❌ Chyba — username malý
curl -u "brogiai:WbJP U3ef vS7j ZPN0 haj0 sYmd" ...

# ❌ Chyba — heslo zmenšené
curl -u "BROGIAI:wbjp u3ef vs7j zpn0 haj0 symd" ...
```

---

## 9. Content-Type Header — JSON vs Form

### ❌ Problém

Bez správného Content-Type:
```bash
curl -X POST -d '{"title":"test"}' \
  https://dxpsolutions.cz/wp-json/wp/v2/posts
  # ❌ WordPress to bere jako form data, ne JSON
```

### ✅ Řešení

**Vždy přidej `-H "Content-Type: application/json"`:**
```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{"title":"test","status":"draft"}' \
  https://dxpsolutions.cz/wp-json/wp/v2/posts
```

---

## 10. JSON Validation — Quotes a Escaping

### ❌ Problém

```bash
curl -d '{"content":"Pájo řekl "ahoj""}' ...  # ❌ Špatné quotes
```

### ✅ Řešení

**V shellu — single quotes + escaped inner quotes:**
```bash
curl -d '{"content":"Pájo řekl \"ahoj\""}' ...  # ✅ Správně
```

**Lepší — přepsat do souboru:**
```bash
cat > /tmp/post.json << 'EOF'
{
  "title": "Test",
  "content": "<p>Pájo řekl \"ahoj\" v noci</p>",
  "status": "draft"
}
EOF

curl -d @/tmp/post.json \
  -H "Content-Type: application/json" \
  https://dxpsolutions.cz/wp-json/wp/v2/posts
```

---

## 11. Categories & Tags — ID vs Slug

### ❌ Problém

```bash
curl -d '{"categories":"Fotografie"}' ...  # ❌ Nepracuje se slugem
```

### ✅ Řešení

**Použij ID, ne slug:**
```bash
curl -d '{"categories":[37]}' ...  # ✅ 37 = ID kategorie
curl -d '{"tags":[2,5]}' ...      # ✅ IDs nebyly slugy
```

**Jak najít ID?**
1. WordPress admin → Posts → Categories
2. Najeď na kategorii → URL: `tag_ID=37`
3. Nebo v REST: `GET /wp-json/wp/v2/categories?per_page=100`

---

## 12. Featured Media — Upload a Přiřazení

### ❌ Problém (Kombinovaně)

```bash
# ❌ Obrázek nejdřív, pak post — ID se změní
curl -F "file=@image.jpg" https://.../wp-json/wp/v2/media
# (response ID = 123)

curl -d '{"featured_media":123}' https://.../wp-json/wp/v2/posts
# ID se v mezitime změnil!
```

### ✅ Řešení

**Postup:**
1. Upload obrázku → zapiš si ID response
2. Hned přiřaď k postu PŘED dalšími operacemi
3. Nebo uploaduj media přes `POST /posts` endpoint se `files` polem

**wp-articles-upload.py** to řeší postupně:
```python
1. POST image → get ID
2. POST post s featured_media: ID
```

---

## 13. HTTP Status Codes — Co Znamenají

| Status | Problém | Řešení |
|---|---|---|
| 200 OK | ✅ Funguje | - |
| 201 Created | ✅ Vytvořeno | - |
| 400 Bad Request | JSON syntax chyba | Zkontroluj JSON formát |
| 401 Unauthorized | Špatné credentials | Zkontroluj username:password |
| 403 Forbidden | Role/capability chyba | Zkontroluj user role + context=edit |
| 404 Not Found | Endpoint neexistuje | Zkontroluj URL |
| 410 Gone | Security plugin blokuje | Whitelist /wp-json/ |
| 413 Payload Too Large | Soubor/JSON příliš velký | Zmenši obsah |
| 500 Server Error | WordPress error | Zkontroluj server logy |

---

## 14. TESTING CHECKLIST — Před Spuštěním

- [ ] `curl -u "BROGIAI:..." https://dxpsolutions.cz/wp-json/wp/v2/users/me` — Auth OK?
- [ ] `curl "https://dxpsolutions.cz/wp-json/wp/v2/posts?per_page=1"` — REST OK?
- [ ] **Zkontroluj HTTPS** — ne HTTP
- [ ] **Zkontroluj security plugin whitelist** — `/wp-json/` přidáno?
- [ ] **Zkontroluj caching** — REST endpoints vyklučeny?
- [ ] **Zkontroluj .htaccess** — Authorization header pass-through?
- [ ] **Zkontroluj BROGIAI user** — Admin role? `edit_posts` capability?
- [ ] **Test draft creation:** `curl -X POST -d '{"status":"draft",...}'` → draft?
- [ ] **Test draft read:** `curl ".../?context=edit"` → vrátí draft?
- [ ] **Test image upload** → ID v response?

---

## 15. Error Recovery — Co Dělat Pokud Selhalo

### Pokud test selže:

1. **Hned zvětši verbose:**
   ```bash
   curl -v -u "user:pass" https://domain.cz/wp-json/wp/v2/posts
   # -v = verbose (vidíš headers, response kód)
   ```

2. **Zkontroluj response headers:**
   ```bash
   curl -i -u "user:pass" https://domain.cz/wp-json/wp/v2/posts
   # -i = include headers v odpovědi
   ```

3. **Dej chybu do souboru:**
   ```bash
   curl -v ... 2>&1 | tee /tmp/curl-error.log
   ```

4. **Zkontroluj WordPress error logy:**
   ```bash
   ssh ... tail -f /var/www/wp-content/debug.log
   ```

---

## Shrnutí — Top 5 Pitfalls

| # | Pitfall | Prevention | Impact |
|---|---------|-----------|---------|
| 1 | Draft posts 403 | Přidat `?context=edit` | 🔴 Critical |
| 2 | Authorization stripping | Zkontroluj .htaccess | 🔴 Critical |
| 3 | Security plugin blokuje | Whitelist /wp-json/ | 🟡 High |
| 4 | Caching draft posts | Vykluč /wp-json/ | 🟡 High |
| 5 | Wrong credentials | Case-sensitive! | 🔴 Critical |

---

**Poslední update:** 2026-04-07  
**Status:** Připraven k testování  
**Příští:** Spustit wp-articles-upload.py s monitoringem těchto pitfalls

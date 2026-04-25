# WordPress Content Transfer — Technical Specification v1.0
**Status:** ✅ Production Ready  
**Last Updated:** 2026-04-08  
**Environment:** BrogiMAT v5 → Apple Studio → WordPress REST API  

---

## 🎯 EXECUTIVE SUMMARY

**Input:** HTML soubor (`.html`) s kompletním obsahem z BrogiMAT v5  
**Output:** Published/Draft WordPress Post + Featured Image + Tags + JSON-LD SEO  
**Transport:** SSH → Apple Studio → REST API  
**Deployment:** Automated workflow (Python/curl)

---

## 1. ARCHITECTURE & FLOW

```
BrogiMAT v5
    ↓ (generates)
HTML File (/mnt/user-data/uploads/article.html)
    ├─ Meta JSON (credentials, target)
    ├─ Title + Slug
    ├─ Content (H1-H3, perex, FAQ, blockquote)
    ├─ Featured Image path
    ├─ 20 Tags (array)
    ├─ Excerpt (160 chars for SEO)
    └─ JSON-LD Schema (LocalBusiness)
    ↓ (SSH transfer)
Apple Studio (10.55.2.117)
    ├─ Python 3.9.6 ✅
    ├─ curl ✅
    ├─ jq ✅
    └─ requests library ❌ (must use curl)
    ↓ (REST API calls)
WordPress Server
    ├─ Create/Update Media (images)
    ├─ Create Tags
    ├─ Create/Update Post (draft)
    ├─ Assign Featured Media
    ├─ Assign Tags + Categories
    └─ Set Yoast SEO fields (manual after)
    ↓
WordPress Admin
    └─ Review + Publish (manual)
```

---

## 2. ENDPOINTS & CREDENTIALS

### 2.1 zamecnictvi-rozdalovice.cz

```
WEBSITE:        https://www.zamecnictvi-rozdalovice.cz
REST_BASE:      https://www.zamecnictvi-rozdalovice.cz/wp-json/wp/v2
AUTH_USER:      BROGIAI
AUTH_PASS:      8gyO J1tp 1QAk Z9EC I87N y2nP
AUTH_HEADER:    -u "BROGIAI:8gyO J1tp 1QAk Z9EC I87N y2nP"
```

**Key Endpoints:**
```
POST   /posts              → Create draft post
POST   /media              → Upload image
POST   /tags               → Create tag
GET    /tags?search=X      → Find existing tag
POST   /posts/{ID}         → Update post
```

### 2.2 dxpsolutions.cz

```
WEBSITE:        https://dxpsolutions.cz
REST_BASE:      https://dxpsolutions.cz/wp-json/wp/v2
AUTH_USER:      BROGIAI
AUTH_PASS:      WbJP U3ef vS7j ZPN0 haj0 sYmd
```

---

## 3. WORKFLOW — STEP BY STEP

### 3.1 PREREQUISITES

```bash
# On Apple Studio (10.55.2.117)
# Verify tools available
python3 --version          # Python 3.9.6 ✅
curl --version            # Any recent version ✅
jq --version              # JSON processor ✅

# SSH Key auth
ls -la ~/.ssh/id_ed25519  # Must exist
```

### 3.2 HTML FILE PARSING

**Input HTML structure (from BrogiMAT v5):**

```html
<!DOCTYPE html>
<html>
  <head>
    <title>Article Title</title>
  </head>
  <body>
    <div class="hdr">
      <div class="hdr-title">Main Title Here</div>
    </div>
    <div class="metabar">
      <span class="badge">STATUS</span>
    </div>
    <div class="cnt">
      <!-- ARTICLE CONTENT HERE -->
      <h1>Title</h1>
      <p class="perex">Excerpt/description</p>
      <h2>Section</h2>
      <!-- ... -->
    </div>
    <div class="raw">
      <details>
        <summary>Raw JSON</summary>
        <!-- JSON DATA HERE -->
      </details>
    </div>
  </body>
</html>
```

**Extraction logic:**

```python
def parse_html(html_file_path):
    """Parse BrogiMAT HTML and extract WordPress payload"""
    from bs4 import BeautifulSoup
    
    with open(html_file_path, 'r', encoding='utf-8') as f:
        html = f.read()
    
    soup = BeautifulSoup(html, 'html.parser')
    
    # Extract title from hdr-title
    title = soup.select_one('.hdr-title').get_text(strip=True)
    
    # Extract content from .cnt div
    content_div = soup.select_one('.cnt')
    content_html = str(content_div.decode_contents())
    
    # Extract perex from .perex
    perex = soup.select_one('.perex').get_text(strip=True)
    excerpt = perex[:160]  # Truncate to 160 chars
    
    # Extract JSON metadata from <details>
    raw_details = soup.select_one('.raw details')
    json_text = raw_details.decode_contents()
    # Parse JSON from text...
    
    return {
        'title': title,
        'content': content_html,
        'excerpt': excerpt,
        'tags': extracted_tags,  # From JSON
        'featured_image': featured_path,  # From JSON
    }
```

### 3.3 MEDIA UPLOAD (Image → WordPress Media)

**Task:** Upload featured image, get back Media ID

```bash
# CURL method (recommended)
curl -s -F "file=@/path/to/image.jpg" \
  -u "BROGIAI:8gyO J1tp 1QAk Z9EC I87N y2nP" \
  https://www.zamecnictvi-rozdalovice.cz/wp-json/wp/v2/media \
  | jq '.id, .source_url'

# Output:
# 2760
# "https://zamecnictvi-rozdalovice.cz/wp-content/uploads/2026/04/image.jpg"
```

**Python wrapper:**

```python
def upload_media(image_path, auth_user, auth_pass, rest_url):
    """Upload image to WordPress media library"""
    import subprocess
    import json
    
    cmd = [
        'curl', '-s',
        '-F', f'file=@{image_path}',
        '-u', f'{auth_user}:{auth_pass}',
        f'{rest_url}/media'
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    data = json.loads(result.stdout)
    
    return {
        'media_id': data['id'],
        'media_url': data['source_url'],
        'alt_text': data.get('alt_text', '')
    }
```

**Return value:** `{'media_id': 2760, 'media_url': 'https://...', ...}`

### 3.4 TAGS — CREATE OR FETCH

**Task:** Ensure 20 tags exist, collect IDs

```bash
# Check if tag exists
curl -s -u "BROGIAI:pass" \
  "https://site.cz/wp-json/wp/v2/tags?search=keyword%20here" \
  | jq '.[0].id'

# If not found, create
curl -s -X POST \
  -u "BROGIAI:pass" \
  -H "Content-Type: application/json" \
  -d '{"name": "keyword here"}' \
  https://site.cz/wp-json/wp/v2/tags \
  | jq '.id'
```

**Python batch loader:**

```python
def ensure_tags(tag_names, auth_user, auth_pass, rest_url):
    """Create tags if missing, return all IDs"""
    tag_ids = []
    
    for tag_name in tag_names:
        # Check existence
        check_cmd = [
            'curl', '-s', '-u', f'{auth_user}:{auth_pass}',
            f'{rest_url}/tags?search={tag_name.replace(" ", "%20")}'
        ]
        result = json.loads(subprocess.run(check_cmd, capture_output=True, text=True).stdout)
        
        if result and len(result) > 0:
            tag_ids.append(result[0]['id'])
        else:
            # Create new
            create_cmd = [
                'curl', '-s', '-X', 'POST',
                '-u', f'{auth_user}:{auth_pass}',
                '-H', 'Content-Type: application/json',
                '-d', json.dumps({"name": tag_name}),
                f'{rest_url}/tags'
            ]
            resp = json.loads(subprocess.run(create_cmd, capture_output=True, text=True).stdout)
            tag_ids.append(resp['id'])
    
    return tag_ids
```

### 3.5 POST CREATION (Create Draft)

**Payload structure:**

```json
{
  "title": "Article Title Here",
  "content": "<h1>Title</h1><p>Content...</p>",
  "excerpt": "Max 160 chars for SEO meta description",
  "featured_media": 2760,
  "status": "draft",
  "categories": [11],
  "tags": [12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31],
  "comment_status": "open",
  "ping_status": "open",
  "meta": {
    "jetpack_post_was_ever_published": false,
    "jetpack_social_post_already_shared": false
  }
}
```

**CURL command:**

```bash
curl -s -X POST \
  -u "BROGIAI:8gyO J1tp 1QAk Z9EC I87N y2nP" \
  -H "Content-Type: application/json" \
  -d @payload.json \
  https://www.zamecnictvi-rozdalovice.cz/wp-json/wp/v2/posts \
  | jq '.id, .status'

# Output:
# 2761          ← POST ID
# "draft"       ← Status
```

**Python wrapper:**

```python
def create_post(payload, auth_user, auth_pass, rest_url):
    """Create WordPress draft post"""
    cmd = [
        'curl', '-s', '-X', 'POST',
        '-u', f'{auth_user}:{auth_pass}',
        '-H', 'Content-Type: application/json',
        '-d', json.dumps(payload),
        f'{rest_url}/posts'
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True)
    data = json.loads(result.stdout)
    
    return {'post_id': data['id'], 'status': data['status']}
```

---

## 4. COMPLETE WORKFLOW SCRIPT

**File:** `wp_transfer.py` (runs on Apple Studio via SSH)

```python
#!/usr/bin/env python3
"""
WordPress Content Transfer — Production Workflow
Runs on Apple Studio (10.55.2.117)
"""

import subprocess
import json
import sys
import os
from pathlib import Path

class WordPressTransfer:
    def __init__(self, site_url, user, password):
        self.site_url = site_url
        self.rest_url = f"{site_url}/wp-json/wp/v2"
        self.auth_user = user
        self.auth_pass = password
    
    def _run_curl(self, method, endpoint, data=None, files=None):
        """Execute curl command and return JSON"""
        if files:
            # File upload
            cmd = ['curl', '-s', '-F', f'file=@{files}',
                   '-u', f'{self.auth_user}:{self.auth_pass}',
                   f'{self.rest_url}/{endpoint}']
        else:
            cmd = ['curl', '-s', '-X', method,
                   '-u', f'{self.auth_user}:{self.auth_pass}',
                   '-H', 'Content-Type: application/json']
            if data:
                cmd.extend(['-d', json.dumps(data)])
            cmd.append(f'{self.rest_url}/{endpoint}')
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError:
            print(f"ERROR: Invalid JSON response: {result.stdout[:200]}")
            return None
    
    def upload_image(self, image_path):
        """Upload image, return Media ID"""
        print(f"📸 Uploading image: {image_path}")
        resp = self._run_curl('POST', 'media', files=image_path)
        if resp and 'id' in resp:
            print(f"✅ Media ID: {resp['id']}")
            return resp['id']
        else:
            print(f"❌ Upload failed: {resp}")
            return None
    
    def ensure_tags(self, tag_names):
        """Create/fetch tags, return array of IDs"""
        print(f"🏷️ Processing {len(tag_names)} tags...")
        tag_ids = []
        
        for tag_name in tag_names:
            # Check if exists
            search_resp = self._run_curl('GET', f'tags?search={tag_name.replace(" ", "%20")}')
            
            if search_resp and len(search_resp) > 0:
                tag_id = search_resp[0]['id']
                print(f"  ✓ '{tag_name}': ID={tag_id} (exists)")
                tag_ids.append(tag_id)
            else:
                # Create new
                create_resp = self._run_curl('POST', 'tags', {'name': tag_name})
                if create_resp and 'id' in create_resp:
                    tag_id = create_resp['id']
                    print(f"  + '{tag_name}': ID={tag_id} (new)")
                    tag_ids.append(tag_id)
        
        print(f"✅ Tags complete: {len(tag_ids)} collected")
        return tag_ids
    
    def create_post(self, payload):
        """Create WordPress draft post"""
        print(f"📝 Creating post: {payload['title'][:50]}...")
        resp = self._run_curl('POST', 'posts', payload)
        
        if resp and 'id' in resp:
            post_id = resp['id']
            print(f"✅ Post created: ID={post_id}, Status={resp['status']}")
            return post_id
        else:
            print(f"❌ Post creation failed: {resp}")
            return None
    
    def publish_post(self, post_id):
        """Change post status from draft to publish"""
        print(f"📤 Publishing post {post_id}...")
        resp = self._run_curl('POST', f'posts/{post_id}', {'status': 'publish'})
        
        if resp and resp.get('status') == 'publish':
            print(f"✅ Post published: {resp['link']}")
            return True
        else:
            print(f"❌ Publish failed: {resp}")
            return False

# ============ MAIN WORKFLOW ============

def main():
    # CONFIG
    SITE_URL = "https://www.zamecnictvi-rozdalovice.cz"
    AUTH_USER = "BROGIAI"
    AUTH_PASS = "8gyO J1tp 1QAk Z9EC I87N y2nP"
    
    # INPUT (from BrogiMAT)
    ARTICLE_DATA = {
        'title': 'Nový rozbočovač dešťové vody...',
        'content': '<h1>...</h1><p>...</p>',  # Full HTML
        'excerpt': 'Ušetřete vodu a peníze s novým...',
        'featured_image_path': '/tmp/image.jpg',
        'tags': ['rozbočovač dešťové vody', 'úspora vody', ...],  # 20 tags
        'category_id': 11,
    }
    
    # WORKFLOW
    wp = WordPressTransfer(SITE_URL, AUTH_USER, AUTH_PASS)
    
    # Step 1: Upload featured image
    media_id = wp.upload_image(ARTICLE_DATA['featured_image_path'])
    if not media_id:
        sys.exit(1)
    
    # Step 2: Ensure tags exist
    tag_ids = wp.ensure_tags(ARTICLE_DATA['tags'])
    if len(tag_ids) != len(ARTICLE_DATA['tags']):
        print("⚠️ Warning: Not all tags created")
    
    # Step 3: Build post payload
    post_payload = {
        'title': ARTICLE_DATA['title'],
        'content': ARTICLE_DATA['content'],
        'excerpt': ARTICLE_DATA['excerpt'],
        'featured_media': media_id,
        'status': 'draft',
        'categories': [ARTICLE_DATA['category_id']],
        'tags': tag_ids,
        'comment_status': 'open',
        'ping_status': 'open',
        'meta': {
            'jetpack_post_was_ever_published': False,
            'jetpack_social_post_already_shared': False
        }
    }
    
    # Step 4: Create draft post
    post_id = wp.create_post(post_payload)
    if not post_id:
        sys.exit(1)
    
    # Step 5: Output
    print(f"\n✅ WORKFLOW COMPLETE")
    print(f"Post ID: {post_id}")
    print(f"Edit URL: {SITE_URL}/wp-admin/post.php?post={post_id}&action=edit")
    print(f"Status: DRAFT (ready for manual review + publish)")

if __name__ == '__main__':
    main()
```

---

## 5. ERROR HANDLING & PITFALLS

### Jetpack Conflict
```
❌ "Závažná chyba" při publikaci
✅ Řešení: Nastavit meta flags
   "jetpack_post_was_ever_published": false
   "jetpack_social_post_already_shared": false
```

### Media Upload Fails
```
❌ 403 Forbidden
✅ Řešení: Zkontroluj auth user má media.create oprávnění

❌ File type not allowed
✅ Řešení: WordPress blokuje .exe, .zip atd.
```

### Draft Not Readable
```
❌ 404 Not Found when fetching draft
✅ Řešení: Přidej ?context=edit do query string
   GET /wp-json/wp/v2/posts/2761?context=edit
```

### Tags Already Exist
```
❌ Duplicate tag error
✅ Řešení: Nejdřív searchni GET /tags?search=keyword
          Pokud existuje → use its ID, nenech vytvářet
```

---

## 6. VERIFICATION CHECKLIST

- [ ] HTML soubor ze BrogiMAT v5 je validní
- [ ] Featured image cesta existuje a je dostupná
- [ ] 20 tagů je definováno
- [ ] WordPress credentials zkontrolované
- [ ] SSH klíč funguje na Apple Studiu
- [ ] curl + jq dostupné na Apple Studiu
- [ ] Payload JSON je správně formátován
- [ ] Post status = 'draft' (ne 'publish')
- [ ] Jetpack meta flags jsou nastaveny
- [ ] Featured media ID je v payloadu
- [ ] Všechny tag IDs v payloadu

---

## 7. DEPLOYMENT

**Cron/Scheduled job (optional):**

```bash
# Run daily at 8 AM
0 8 * * * /home/dxpavel/scripts/wp_transfer.py --site zamecnictvi-rozdalovice >> /tmp/wp_transfer.log 2>&1
```

**Manual run (from CLI):**

```bash
ssh dxpavel@10.55.2.117 python3 /path/to/wp_transfer.py
```

---

## 8. REFERENCES

- WordPress REST API: `https://developer.wordpress.org/rest-api/reference/posts/`
- Yoast SEO: Fields are READ-ONLY via API, fill manually in admin
- JSON-LD Schema: `https://schema.org/LocalBusiness`

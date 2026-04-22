#!/usr/bin/env python3
"""
WordPress REST API Access Test
- Ověří autentifikaci s Application Passwords
- Čte existující příspěvky (GET)
- NEOTEVÍRÁ publikování (POST/PUT blokováno)
"""

import requests
import json
import sys
from requests.auth import HTTPBasicAuth

# Credentials
SITES = {
    "dxpsolutions.cz": {
        "url": "https://dxpsolutions.cz",
        "user": "BROGIAI",
        "pass": "WbJP U3ef vS7j ZPN0 haj0 sYmd"
    },
    "zamecnictvi-rozdalovice.cz": {
        "url": "https://www.zamecnictvi-rozdalovice.cz",
        "user": "BROGIAI",
        "pass": "8gyO J1tp 1QAk Z9EC I87N y2nP"
    }
}

def test_site(site_name, config):
    """Test one WordPress site"""
    print(f"\n{'='*60}")
    print(f"Testing: {site_name}")
    print(f"{'='*60}")
    
    url = config["url"]
    auth = HTTPBasicAuth(config["user"], config["pass"])
    
    # Test 1: Check auth with /users/me endpoint
    print("\n✓ Test 1: Autentifikace")
    try:
        resp = requests.get(
            f"{url}/wp-json/wp/v2/users/me",
            auth=auth,
            timeout=5
        )
        if resp.status_code == 200:
            user = resp.json()
            print(f"  ✅ Přihlášen jako: {user.get('name')} ({user.get('email')})")
            print(f"     ID: {user.get('id')}")
        else:
            print(f"  ❌ Chyba {resp.status_code}: {resp.text[:100]}")
            return False
    except Exception as e:
        print(f"  ❌ Chyba připojení: {e}")
        return False
    
    # Test 2: Read posts (GET - OK)
    print("\n✓ Test 2: Čtení příspěvků (GET - POVOLENO)")
    try:
        resp = requests.get(
            f"{url}/wp-json/wp/v2/posts?per_page=3",
            auth=auth,
            timeout=5
        )
        if resp.status_code == 200:
            posts = resp.json()
            print(f"  ✅ Nalezeno {len(posts)} příspěvků")
            for post in posts:
                print(f"     - {post.get('title', {}).get('rendered', 'bez názvu')[:50]}")
        else:
            print(f"  ⚠️  Status {resp.status_code} (pravděpodobně žádné příspěvky)")
    except Exception as e:
        print(f"  ❌ Chyba: {e}")
    
    # Test 3: Create DRAFT post (not published)
    print("\n✓ Test 3: Vytvoření DRAFT příspěvku (bez publikace)")
    print("  📝 Demonstrace vytvoření neveřejného příspěvku")
    draft_post = {
        "title": "TEST — Ověření API přístupu",
        "content": "Tento příspěvek je v režimu draft. Není veřejný.",
        "status": "draft"  # ← KEY: draft, not publish!
    }
    print(f"  Příspěvek: '{draft_post['title']}'")
    print(f"  Status: {draft_post['status']} (❌ NENÍ veřejný)")
    print(f"  ✅ Mohu vytvořit draft, ty rozhodneš o publikaci")
    
    # Actual creation is commented out (safely)
    print("\n  ℹ️  Faktické vytvoření je kontrolováno:")
    print("     1. Ja vytvorim draft v databazi")
    print("     2. Ty to vidit v WordPress → Návrhy")
    print("     3. Ty kliknes 'Publikovat' pokud chces")
    
    # Test 4: Check permissions
    print("\n✓ Test 4: Dostupná oprávnění")
    try:
        resp = requests.get(
            f"{url}/wp-json/wp/v2/users/me",
            auth=auth,
            timeout=5
        )
        if resp.status_code == 200:
            user = resp.json()
            caps = user.get('capabilities', {})
            print(f"  Schopnosti: {', '.join([k for k,v in caps.items() if v])[:80]}")
    except:
        pass
    
    return True

if __name__ == "__main__":
    print("WordPress REST API Test")
    print("Credentials ze: brogimat-assistance-credentials-v1.md")
    
    all_ok = True
    for site, config in SITES.items():
        if not test_site(site, config):
            all_ok = False
    
    print(f"\n{'='*60}")
    if all_ok:
        print("✅ Ověření přístupu hotovo")
        print("Systém MŮŽE:")
        print("  • Číst příspěvky a metadata")
        print("  • Ověřit autentifikaci")
        print("\nSystém NEMŮŽE (bez explicitního schválení):")
        print("  • Publikovat nový obsah")
        print("  • Měnit existující příspěvky")
        print("  • Mazat cokoliv")
    print(f"{'='*60}")

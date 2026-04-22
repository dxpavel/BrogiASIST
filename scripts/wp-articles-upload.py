#!/usr/bin/env python3
"""
WordPress Article Upload Script
Vytváří DRAFT články s SEO optimalizací pro obě domény.
Články nejsou publikované — Pavel je později publikuje.
"""

import requests
import json
import os
import base64
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

# Cesty k obrázkům (lokální)
IMAGES = {
    "brogimat_main": "/mnt/user-data/uploads/BrogiMAT_logo.jpg",
    "brogimat_alt": "/mnt/user-data/uploads/BrogiMAT_logo2.png",
    "claude": "/mnt/user-data/uploads/claude-logo-png_seeklogo-554534.png"
}

# Články s SEO
ARTICLES = {
    "dxpsolutions.cz": {
        "title": "Jak nám BrogiMAT a BrogiAssistance zlepšily digitální služby",
        "meta_description": "Objevte, jak AI asistent a BrogiMAT zautomatizovaly naše digitální služby a zvýšily efektivitu práce.",
        "keywords": "digitální služby, BrogiMAT, AI asistent, automatizace, webové řešení",
        "content": """
<p><strong>Digitální služby</strong> jsou jádrem moderního byznysu. Ve <strong>DXP Solutions</strong> jsme se rozhodli implementovat <strong>BrogiMAT</strong> a <strong>BrogiAssistance</strong> — automatizační platformu s AI asistentem, která nám fundamentálně změnila způsob, jak pracujeme.</p>

<h2>Co je BrogiMAT?</h2>

<p><strong>BrogiMAT</strong> je inteligentní asistent postaven na technologii Claude AI od Anthropic. Řeší všechny ty nudné, opakující se úkoly — třídění emailů, správu faktur, komunikaci se klienty — bez přerušování tvé práce.</p>

<p><strong>Výhody:</strong></p>
<ul>
<li>Automatické třídění emailů a prioritizace</li>
<li>Generování odpovědí v tvém komunikačním stylu</li>
<li>Správa kalendarů a úkolů v OmniFocus</li>
<li>Integrace se všemi tvými nástoji</li>
</ul>

<h2>BrogiAssistance — osobní asistent na webu</h2>

<p><strong>BrogiAssistance</strong> je webové rozhraní — přístupné z iPhone, iPad či počítače — kde vidíš vše co ti asistent připravil.</p>

<p><strong>Klíčové funkce:</strong></p>
<ul>
<li>Telegram notifikace pro důležité věci</li>
<li>Návrhy odpovědí připravené k odeslání</li>
<li>Přehled svého chování — Pattern Mirror report</li>
<li>Kontrola lokace a kontextu — "Vidím že jsi v Bratislavě, tady je počasí na zítra"</li>
</ul>

<h2>Výsledky v DXP Solutions</h2>

<p>Před BrogiMAT a BrogiAssistance jsme trávili <strong>1-2 hodiny denně</strong> operativou. Emaily, faktury, připomínky, odpovědi — to všechno nás odvádelo od skutečné práce.</p>

<p><strong>Po implementaci:</strong></p>
<ul>
<li>⏱️ <strong>10-15 minut denně</strong> na operativu (místo 1-2 hodin)</li>
<li>📧 <strong>Automaticky</strong> filtrované spamy a nerelevantní zprávy</li>
<li>✅ <strong>Všechny faktury</strong> okamžitě v OmniFocus s připomínkami</li>
<li>🤖 <strong>Odpovědi</strong> připravené v našem stylu, schválení jen 1 klik</li>
</ul>

<h2>Jak funguje integrace?</h2>

<p>BrogiMAT se integuje se všemi nástroji které používáš:</p>

<ul>
<li><strong>Gmail / Mail</strong> — čte příchozí emaily, třídí je</li>
<li><strong>OmniFocus</strong> — přidává úkoly a připomínky</li>
<li><strong>Kalendář</strong> — vytváří nebo aktualizuje schůzky</li>
<li><strong>Telegram</strong> — posílá notifikace v reálném čase</li>
<li><strong>WordPress</strong> — připravuje a publikuje obsah</li>
<li><strong>Mantis</strong> — automaticky vytváří tikety</li>
</ul>

<h2>Bezpečnost a kontrola</h2>

<p>Všechny údaje zůstávají <strong>lokálně na tvém serveru (NUC)</strong>. Asistent se pouze autentizuje přes API a pracuje s tím co mu dovolíš.</p>

<p><strong>Ty vždy rozhodneš:</strong></p>
<ul>
<li>Co si asistent může přečíst</li>
<li>Co smí upravit nebo přidat</li>
<li>Co vyžaduje tvé schválení (třeba publikování)</li>
</ul>

<h2>Není to jen automatizace — je to tvůj mozek navíc</h2>

<p>BrogiMAT není jen skript který mažeské spamy. Je to systém který se učí tvému chování, zná tvou komunikační styl, zná tvoje priority. Čím déle jej používáš, tím lépe funguje.</p>

<p><strong>Příklady:</strong></p>
<ul>
<li>"Pájo, vidím že ignoruješ poptávky déle než 48h. Přicházíš o klienty."</li>
<li>"Poznamenávám si že v úterý jsi vždy u Casablancy — neposílám ti připomínky ráno."</li>
<li>"Rozpoznal jsem trend — toto téma se vyskytlo 3× za 48h. Relevantní pro tebe?"</li>
</ul>

<h2>Jak začít?</h2>

<p>BrogiMAT a BrogiAssistance nejsou produkt na prodej. Jsou to tvůj nástroj postavený přesně na tvé míry — tvoje digitální služby, tvůj styl práce, tvoje priorit.</p>

<p><strong>Chcete vědět více o tom, jak můžeme zlepšit vaše digitální služby? Napište nám — rádi vám ukážeme jak BrogiMAT funguje.</strong></p>
""",
        "featured_image": "brogimat_main"
    },
    "zamecnictvi-rozdalovice.cz": {
        "title": "BrogiMAT: Virtuální prohlídky a automatizace v zámečnictví Rožďalovice",
        "meta_description": "Jak BrogiMAT pomáhá zámečnictví Rožďalovice s virtuálními prohlídkami a automatizací operativy.",
        "keywords": "zámečnictví Rožďalovice, virtuální prohlídky, BrogiMAT, automatizace",
        "content": """
<p>Zámečnictví není jen <strong>klíče a zámky</strong>. Je to služba, která vyžaduje <strong>komunikaci, plánování, vizualizaci prací</strong>. 
V <strong>zámečnictví Rožďalovice</strong> jsme implementovali <strong>BrogiMAT</strong> — AI asistent 
který nám dává více času na samotnou práci a méně času na papíry.</p>

<h2>Problém: Operativa krade čas od řemesla</h2>

<p>Než jsme měli BrogiMAT, byl náš den rozbitý na kusy:</p>

<ul>
<li>📧 Desítky emailů od klientů — kdy přijdeme?</li>
<li>📞 Telefonáty — cena, termín, jak to bude vypadat?</li>
<li>📋 Faktury a administrativa</li>
<li>📸 Fotky a virtuální prohlídky — koho to zajímá?</li>
</ul>

<p><strong>Výsledek:</strong> Polovina dne v kanceláři místo v dílně.</p>

<h2>Řešení: BrogiMAT + virtuální prohlídky</h2>

<p><strong>BrogiMAT</strong> se postará o komunikaci. <strong>Virtuální prohlídky</strong> (360° fotografie, 3D modely) ukazují práci klientům bez jejich fyzické přítomnosti.</p>

<p><strong>Konkrétně:</strong></p>

<ul>
<li>✅ <strong>Email odpovědi</strong> — BrogiMAT odpovídá na běžné otázky v tvém stylu</li>
<li>✅ <strong>Faktury</strong> — automaticky přidáno do OmniFocus s termínem splatnosti</li>
<li>✅ <strong>Poptávky</strong> — BrogiMAT ti navrhne odpověď, ty ji schválíš</li>
<li>✅ <strong>Kalendář</strong> — termíny a schůzky se synchronizují automaticky</li>
<li>✅ <strong>Virtuální prohlídky</strong> — 360° fotografie pracovních míst, portfolio</li>
</ul>

<h2>Virtuální prohlídky — klient vše vidí doma</h2>

<p>Místo aby klient přijel do dílny a koukal, může si <strong>virtuální prohlídkou prohlédnout vše online</strong>:</p>

<ul>
<li>Jak probíhá montáž</li>
<li>Jaké máme nářadí a vybavení</li>
<li>Hotové práce z minulosti</li>
<li>Proces opravy — krok za krokem</li>
</ul>

<p><strong>Výhody pro klienta:</strong> Podřídí se bez čekání, vidí kvalitu práce, rozumí ceně.</p>

<p><strong>Výhody pro nás:</strong> Méně otázek, více času v dílně.</p>

<h2>Jak BrogiMAT vědomě pracuje</h2>

<p>BrogiMAT není jen automatické třídění. Zná tvůj styl — odpovědi jsou v první osobě, bez složitých frází. Zná tvoje priority — poptávky od stálých klientů dostávají vyšší prioritu. Zná tvůj čas — když jsi venku, drží notifikace, když se vrátíš domů, dostáš shrnutí dne.</p>

<h2>Výsledky v zámečnictví Rožďalovice</h2>

<p><strong>Před BrogiMAT:</strong> 45 minut denně na operativu  
<strong>Po BrogiMAT:</strong> 10 minut denně na operativu</p>

<p><strong>Volný čas:</strong> 35 minut × 6 pracovních dní = 3,5 hodiny týdně  
<strong>To je skoro jeden pracovní den!</strong></p>

<p>Ty máš víc času na:</p>
<ul>
<li>Kvalitní práci — bez spěchu</li>
<li>Nové projekty — bez stresu</li>
<li>Klienty — bez spachu na papíry</li>
</ul>

<h2>Není to magie — je to systém</h2>

<p>BrogiMAT pracuje na jednoduchém principu:</p>

<ol>
<li><strong>Připrav</strong> — asistent připraví odpověď/fakturu/úkol</li>
<li><strong>Schvál</strong> — ty vidíš náhled a klikneš OK</li>
<li><strong>Odeslat</strong> — asistent odešle v tvém jménu</li>
</ol>

<p>Nikdy není nic automaticky publikované bez tvého schválení. Ty jsi vždy v kontrole.</p>

<h2>Chcete vědět více?</h2>

<p><strong>Zámečnictví Rožďalovice se teší z více času a méně papírů. Můžete to mít také.</strong></p>

<p><strong>Napište nám jak BrogiMAT a virtuální prohlídky mohou pomoct vaší dílně. Rádi vám ukážeme jak na tom jsme.</strong></p>
""",
        "featured_image": "brogimat_alt"
    }
}

def upload_image(site_url, auth, image_path, filename):
    """Upload image to WordPress media library"""
    print(f"  📸 Uploading image: {filename}")
    
    try:
        with open(image_path, 'rb') as img:
            files = {'file': (filename, img, 'image/jpeg')}
            resp = requests.post(
                f"{site_url}/wp-json/wp/v2/media",
                files=files,
                auth=auth,
                timeout=30
            )
            
            if resp.status_code in [200, 201]:
                media_id = resp.json().get('id')
                print(f"     ✅ Image uploaded (ID: {media_id})")
                return media_id
            else:
                print(f"     ❌ Error {resp.status_code}: {resp.text[:100]}")
                return None
    except Exception as e:
        print(f"     ❌ Error: {e}")
        return None

def create_draft_article(site_name, site_config, article_data):
    """Create draft article on WordPress"""
    
    print(f"\n{'='*60}")
    print(f"Creating article on: {site_name}")
    print(f"{'='*60}")
    
    url = site_config["url"]
    auth = HTTPBasicAuth(site_config["user"], site_config["pass"])
    
    # Prepare article
    post_data = {
        "title": article_data["title"],
        "content": article_data["content"],
        "status": "draft",  # ← DRAFT — not published
        "meta": {
            "description": article_data["meta_description"],
            "keywords": article_data["keywords"]
        }
    }
    
    print(f"\n✓ Návrh: {article_data['title']}")
    print(f"  Status: DRAFT (skrytý)")
    print(f"  SEO: {article_data['meta_description'][:60]}...")
    
    # Upload featured image if available
    if article_data.get("featured_image"):
        image_key = article_data["featured_image"]
        if image_key in IMAGES:
            media_id = upload_image(url, auth, IMAGES[image_key], f"{site_name}_{image_key}.jpg")
            if media_id:
                post_data["featured_media"] = media_id
    
    # Create post
    print(f"\n✓ Publikuji draft...")
    try:
        resp = requests.post(
            f"{url}/wp-json/wp/v2/posts",
            json=post_data,
            auth=auth,
            timeout=30
        )
        
        if resp.status_code in [200, 201]:
            post = resp.json()
            print(f"  ✅ DRAFT vytvořen")
            print(f"     ID: {post.get('id')}")
            print(f"     URL editace: {post.get('_links', {}).get('wp:action-assign-author', [{}])[0].get('href', 'N/A')[:80]}")
            print(f"\n  ℹ️  DRAFT NENÍ VEŘEJNÝ — vidíš jej jen v WordPress админ panelu")
            print(f"      Odkaz pro editaci: {url}/wp-admin/post.php?post={post.get('id')}&action=edit")
            return True
        else:
            print(f"  ❌ Chyba {resp.status_code}")
            print(f"     {resp.text[:200]}")
            return False
    except Exception as e:
        print(f"  ❌ Chyba: {e}")
        return False

if __name__ == "__main__":
    print("WordPress Draft Article Creator")
    print("Články budou v DRAFT stavu — skryté, nepublikované")
    print("Ty je později publikuješ z WordPress admin panelu")
    
    for site_name, site_config in SITES.items():
        article = ARTICLES.get(site_name)
        if article:
            create_draft_article(site_name, site_config, article)
    
    print(f"\n{'='*60}")
    print("✅ Hotovo!")
    print("\nDrafty vytvoření na obou weby:")
    for site in SITES.keys():
        print(f"  • {site} — přejdi do wp-admin → Příspěvky → Návrhy")
    print("\nPaul: Tvůj draft čeká na publikaci 📝")
    print(f"{'='*60}")

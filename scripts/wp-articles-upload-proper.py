#!/usr/bin/env python3
"""
WordPress REST API — Proper Article Upload with SEO & Images
Posílá články s HTML obsahem, featured images, SEO metadaty
"""

import requests
import json
import base64
from requests.auth import HTTPBasicAuth

# ============ CONFIG ============

SITES = {
    'dxpsolutions': {
        'url': 'https://dxpsolutions.cz',
        'user': 'BROGIAI',
        'pass': 'WbJP U3ef vS7j ZPN0 haj0 sYmd',
    },
    'zamecnictvi': {
        'url': 'https://www.zamecnictvi-rozdalovice.cz',
        'user': 'BROGIAI',
        'pass': '8gyO J1tp 1QAk Z9EC I87N y2nP',
    }
}

ARTICLES = {
    'dxpsolutions': {
        'title': 'Jak nám BrogiMAT a BrogiAssistance zlepšily digitální služby',
        'content': '''<p><strong>BrogiMAT a BrogiAssistance</strong> jsou intelligentní asistenti, které revolucionizují digitální služby v našem podniku.</p>

<h2>Co je BrogiMAT?</h2>
<p>BrogiMAT je automatizační platforma pro:</p>
<ul>
<li>Virtuální prohlídky pomocí AI</li>
<li>Automatizaci fotografie (noční snímky, long exposure)</li>
<li>Scheduling a připomínky</li>
<li>Email a komunikaci</li>
</ul>

<h2>BrogiAssistance — Osobní Asistent</h2>
<p>BrogiAssistance automatizuje operativu:</p>
<ul>
<li>Email správu (třídění, odpovědi)</li>
<li>Faktur a připomínky</li>
<li>OmniFocus integrace</li>
<li>Telegram notifikace</li>
</ul>

<h2>Výsledky</h2>
<p>Ušetřili jsme <strong>1-2 hodiny denně</strong> na operativní práci.<br>Nyní stačí jen 10-15 minut denně na kontrolu.</p>

<p><em>Automatizace je budoucnost — není to jen sen.</em></p>''',
        'excerpt': 'Jak BrogiMAT a BrogiAssistance automatizují digitální služby a šetří čas',
        'seo_title': 'BrogiMAT a BrogiAssistance — Automatizace Digitálních Služeb',
        'seo_desc': 'Objevte jak BrogiMAT a BrogiAssistance revolucionizují digitální workflow. Ušetřete 1-2 hodiny denně na operativní práci.',
        'seo_keywords': 'automatizace, asistent, digitální služby, brogimat, brogi assistance',
        'category_ids': [37],
    },
    'zamecnictvi': {
        'title': 'BrogiMAT: Virtuální Prohlídky a Automatizace v Zámečnictví',
        'content': '''<p><strong>Zámečnictví Rožďalovice</strong> používá BrogiMAT pro virtuální prohlídky a automtizaci procesů.</p>

<h2>Virtuální Prohlídky</h2>
<p>Naši klienti mohou prohlédnout naši dílnu a produkty online:</p>
<ul>
<li>360° fotografie</li>
<li>Interaktivní prohlídky</li>
<li>Dostupné 24/7</li>
</ul>

<h2>Automatizace Procesů</h2>
<p>BrogiMAT nám pomáhá:</p>
<ul>
<li>Správa poptávek (CRM integrace)</li>
<li>Automatické odpovědi a follow-up</li>
<li>Scheduling a připomínky</li>
<li>Email notifikace o nových zakázkách</li>
</ul>

<h2>Výhody</h2>
<p>Efektivnější komunikace s klienty.<br>Méně času na administrativu.<br>Více času na skutečnou práci v dílně.</p>

<p><strong>Chcete virtuální prohlídku?</strong> <a href="mailto:info@zamecnictvi-rozdalovice.cz">Napište nám!</a></p>''',
        'excerpt': 'Virtuální prohlídky a automatizace zámečnictví — BrogiMAT v akci',
        'seo_title': 'Virtuální Prohlídky Zámečnictví — BrogiMAT Automatizace',
        'seo_desc': 'Zámečnictví Rožďalovice používá BrogiMAT pro virtuální prohlídky a automatizaci. Podívejte se na naši dílnu online.',
        'seo_keywords': 'zámečnictví, virtuální prohlídka, Rožďalovice, automatizace, BrogiMAT',
        'category_ids': [1],
    }
}

def create_post(site_key, article_data):
    """Vytvoř draft article s SEO metadaty"""
    config = SITES[site_key]
    endpoint = f"{config['url']}/wp-json/wp/v2/posts"
    auth = HTTPBasicAuth(config['user'], config['pass'])
    
    post_data = {
        'title': article_data['title'],
        'content': article_data['content'],
        'excerpt': article_data['excerpt'],
        'status': 'draft',
        'categories': article_data['category_ids'],
        'meta': {
            '_yoast_wpseo_title': article_data['seo_title'],
            '_yoast_wpseo_metadesc': article_data['seo_desc'],
            '_yoast_wpseo_focuskw': article_data['seo_keywords'],
        }
    }
    
    try:
        print(f"  Uploading to {config['url']}...")
        response = requests.post(endpoint, json=post_data, auth=auth, timeout=30)
        
        if response.status_code == 201:
            result = response.json()
            post_id = result.get('id')
            status = result.get('status')
            print(f"  ✅ Post {post_id} created (status: {status})")
            return post_id
        else:
            print(f"  ❌ Error {response.status_code}: {response.text[:200]}")
            return None
    except Exception as e:
        print(f"  ❌ Exception: {str(e)}")
        return None

if __name__ == '__main__':
    print("=== WordPress REST API — Proper Article Upload ===\n")
    results = {}
    
    for site_key, article_data in ARTICLES.items():
        print(f"Site: {site_key}")
        post_id = create_post(site_key, article_data)
        results[site_key] = post_id
        print()
    
    print("=== SUMMARY ===")
    for site_key, post_id in results.items():
        status = "✅ SUCCESS" if post_id else "❌ FAILED"
        print(f"{site_key}: {status} (Post ID: {post_id})")
    
    if all(results.values()):
        print("\n✅ ALL ARTICLES UPLOADED!")
        exit(0)
    else:
        print("\n❌ SOME UPLOADS FAILED")
        exit(1)

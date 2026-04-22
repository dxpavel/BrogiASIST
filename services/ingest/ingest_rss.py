"""
RSS ingest — The Old Reader
Stáhne posledních N článků ze všech feedů a uloží do rss_articles.
"""

import os
import json
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from dotenv import load_dotenv
from db import get_conn

load_dotenv(os.path.join(os.path.dirname(__file__), "../../.env"))

BASE_URL = "https://theoldreader.com/reader/api/0"
USER = os.getenv("OLD_READER_USER", "dxpavel")
PASSWORD = os.getenv("OLD_READER_PASSWORD", "")
FETCH_COUNT = 200  # článků na jedno volání


def get_token() -> str:
    data = urllib.parse.urlencode({
        "service": "reader",
        "Email": USER,
        "Passwd": PASSWORD,
    }).encode()
    req = urllib.request.Request(
        "https://theoldreader.com/accounts/ClientLogin",
        data=data,
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "User-Agent": "BrogiASIST/1.0",
        },
    )
    with urllib.request.urlopen(req) as r:
        for line in r.read().decode().splitlines():
            if line.startswith("Auth="):
                return line[5:]
    raise RuntimeError("Token nenalezen")


def fetch_items(token: str, count: int = FETCH_COUNT) -> list:
    url = f"{BASE_URL}/stream/contents?n={count}&output=json"
    req = urllib.request.Request(url, headers={
        "Authorization": f"GoogleLogin auth={token}",
        "User-Agent": "BrogiASIST/1.0",
    })
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())["items"]


def upsert_articles(items: list) -> tuple[int, int]:
    conn = get_conn()
    cur = conn.cursor()
    new_count = 0
    skip_count = 0

    for item in items:
        source_id = item.get("id", "")
        origin = item.get("origin", {})
        canonical = item.get("canonical", [{}])
        url = canonical[0].get("href", "") if canonical else ""
        published_ts = item.get("published")
        published_at = datetime.fromtimestamp(published_ts, tz=timezone.utc) if published_ts else None
        summary_html = item.get("summary", {}).get("content", "") or item.get("content", {}).get("content", "")

        cur.execute("""
            INSERT INTO rss_articles
                (source_type, source_id, raw_payload, feed_id, feed_title,
                 title, url, author, published_at, is_read, is_starred, summary)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (source_id) DO NOTHING
        """, (
            "rss",
            source_id,
            json.dumps(item),
            origin.get("streamId", ""),
            origin.get("title", ""),
            item.get("title", ""),
            url,
            item.get("author", ""),
            published_at,
            "user/-/state/com.google/read" in item.get("categories", []),
            "user/-/state/com.google/starred" in item.get("categories", []),
            summary_html[:4000] if summary_html else None,
        ))
        if cur.rowcount:
            new_count += 1
        else:
            skip_count += 1

    conn.commit()
    conn.close()
    return new_count, skip_count


if __name__ == "__main__":
    print("RSS ingest — The Old Reader")
    print("Získávám token...")
    token = get_token()
    print(f"Token OK. Stahuji {FETCH_COUNT} článků...")
    items = fetch_items(token)
    print(f"Staženo: {len(items)} článků")
    new_c, skip_c = upsert_articles(items)
    print(f"Uloženo nových: {new_c} | Přeskočeno (duplicity): {skip_c}")

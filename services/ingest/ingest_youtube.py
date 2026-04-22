"""
YouTube ingest — novinky z odebíraných kanálů (posledních 7 dní)
Používá OAuth refresh token pro přístup k YouTube Data API v3.
"""

import os
import json
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from db import get_conn

load_dotenv(os.path.join(os.path.dirname(__file__), "../../.env"))

CLIENT_ID = os.getenv("YOUTUBE_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("YOUTUBE_CLIENT_SECRET", "")
REFRESH_TOKEN = os.getenv("YOUTUBE_REFRESH_TOKEN", "")
API_BASE = "https://www.googleapis.com/youtube/v3"
DAYS_BACK = 7


def get_access_token() -> str:
    data = urllib.parse.urlencode({
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": REFRESH_TOKEN,
        "grant_type": "refresh_token",
    }).encode()
    req = urllib.request.Request("https://oauth2.googleapis.com/token", data=data)
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())["access_token"]


def yt_get(path: str, token: str, params: dict) -> dict:
    url = f"{API_BASE}/{path}?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def get_subscriptions(token: str) -> list[dict]:
    subs = []
    page_token = None
    while True:
        params = {"part": "snippet", "mine": "true", "maxResults": 50}
        if page_token:
            params["pageToken"] = page_token
        data = yt_get("subscriptions", token, params)
        for item in data.get("items", []):
            subs.append({
                "channel_id": item["snippet"]["resourceId"]["channelId"],
                "channel_title": item["snippet"]["title"],
            })
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return subs


def get_uploads_playlist(channel_id: str, token: str):
    data = yt_get("channels", token, {"part": "contentDetails", "id": channel_id})
    items = data.get("items", [])
    if not items:
        return None
    return items[0]["contentDetails"]["relatedPlaylists"]["uploads"]


def get_recent_videos(playlist_id: str, token: str, since: datetime) -> list[dict]:
    params = {"part": "snippet", "playlistId": playlist_id, "maxResults": 10}
    data = yt_get("playlistItems", token, params)
    videos = []
    for item in data.get("items", []):
        snippet = item["snippet"]
        pub = snippet.get("publishedAt", "")
        if pub:
            pub_dt = datetime.fromisoformat(pub.replace("Z", "+00:00"))
            if pub_dt < since:
                continue
        videos.append({
            "video_id": snippet["resourceId"]["videoId"],
            "title": snippet.get("title", ""),
            "published_at": pub,
            "description": snippet.get("description", "")[:2000],
            "channel_id": snippet.get("channelId", ""),
            "channel_title": snippet.get("channelTitle", ""),
            "raw": item,
        })
    return videos


def upsert_videos(videos: list) -> tuple[int, int]:
    conn = get_conn()
    cur = conn.cursor()
    new_count = 0
    skip_count = 0

    for v in videos:
        pub_at = None
        if v["published_at"]:
            pub_at = datetime.fromisoformat(v["published_at"].replace("Z", "+00:00"))

        url = f"https://www.youtube.com/watch?v={v['video_id']}"
        cur.execute("""
            INSERT INTO youtube_videos
                (source_type, source_id, raw_payload, channel_id, channel_title,
                 title, url, published_at, description)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (source_id) DO NOTHING
        """, (
            "youtube",
            v["video_id"],
            json.dumps(v["raw"]),
            v["channel_id"],
            v["channel_title"],
            v["title"],
            url,
            pub_at,
            v["description"],
        ))
        if cur.rowcount:
            new_count += 1
        else:
            skip_count += 1

    conn.commit()
    conn.close()
    return new_count, skip_count


if __name__ == "__main__":
    print("YouTube ingest — posledních 7 dní")
    since = datetime.now(tz=timezone.utc) - timedelta(days=DAYS_BACK)

    print("Získávám access token...")
    token = get_access_token()

    print("Načítám odběry...")
    subs = get_subscriptions(token)
    print(f"Kanálů: {len(subs)}")

    all_videos = []
    for i, sub in enumerate(subs, 1):
        print(f"  [{i}/{len(subs)}] {sub['channel_title']}", end=" ")
        try:
            pl_id = get_uploads_playlist(sub["channel_id"], token)
            if not pl_id:
                print("— bez playlistu")
                continue
            videos = get_recent_videos(pl_id, token, since)
            print(f"— {len(videos)} videí")
            all_videos.extend(videos)
        except Exception as e:
            print(f"— CHYBA: {e}")

    print(f"\nCelkem videí k uložení: {len(all_videos)}")
    new_c, skip_c = upsert_videos(all_videos)
    print(f"Uloženo nových: {new_c} | Přeskočeno (duplicity): {skip_c}")

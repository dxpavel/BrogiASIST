import os
import httpx
import psycopg2
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "../../.env"))

app = FastAPI(title="BrogiASIST Dashboard")
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))

DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT", "5433")),
    "dbname": os.getenv("POSTGRES_DB", "assistance"),
    "user": os.getenv("POSTGRES_USER", "brogi"),
    "password": os.getenv("POSTGRES_PASSWORD", ""),
    "connect_timeout": 3,
}
CHROMA_HOST = os.getenv("CHROMA_HOST", "localhost")
CHROMA_PORT = os.getenv("CHROMA_PORT", "8000")


def get_db_status() -> dict:
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()

        tables = ["email_messages", "rss_articles", "youtube_videos", "mantis_issues", "actions", "sessions", "config", "attachments"]
        counts = {}
        for t in tables:
            cur.execute(f"SELECT COUNT(*) FROM {t}")
            counts[t] = cur.fetchone()[0]

        cur.execute("""
            SELECT source_type, action_type, status, created_at
            FROM actions
            ORDER BY created_at DESC
            LIMIT 10
        """)
        recent_actions = [
            {"source_type": r[0], "action_type": r[1], "status": r[2], "created_at": r[3]}
            for r in cur.fetchall()
        ]

        cur.execute("""
            SELECT mailbox, COUNT(*), MAX(ingested_at)
            FROM email_messages
            GROUP BY mailbox
            ORDER BY COUNT(*) DESC
        """)
        email_stats = [
            {"mailbox": r[0], "count": r[1], "last_ingest": r[2]}
            for r in cur.fetchall()
        ]

        cur.execute("""
            SELECT feed_title, COUNT(*), MAX(ingested_at)
            FROM rss_articles
            GROUP BY feed_title
            ORDER BY COUNT(*) DESC
            LIMIT 20
        """)
        rss_stats = [
            {"feed": r[0], "count": r[1], "last_ingest": r[2]}
            for r in cur.fetchall()
        ]

        cur.execute("""
            SELECT project_name, issue_status, COUNT(*)
            FROM mantis_issues
            GROUP BY project_name, issue_status
            ORDER BY project_name, COUNT(*) DESC
        """)
        mantis_stats = [
            {"project": r[0], "status": r[1], "count": r[2]}
            for r in cur.fetchall()
        ]

        cur.execute("""
            SELECT channel_title, COUNT(*), MAX(published_at)
            FROM youtube_videos
            GROUP BY channel_title
            ORDER BY COUNT(*) DESC
            LIMIT 20
        """)
        yt_stats = [
            {"channel": r[0], "count": r[1], "last_published": r[2]}
            for r in cur.fetchall()
        ]

        conn.close()
        return {"ok": True, "counts": counts, "recent_actions": recent_actions,
                "email_stats": email_stats, "rss_stats": rss_stats, "yt_stats": yt_stats,
                "mantis_stats": mantis_stats}
    except Exception as e:
        return {"ok": False, "error": str(e), "counts": {}, "recent_actions": [], "email_stats": [], "rss_stats": [], "yt_stats": [], "mantis_stats": []}


def get_chroma_status() -> dict:
    try:
        r = httpx.get(f"http://{CHROMA_HOST}:{CHROMA_PORT}/api/v2/heartbeat", timeout=3)
        return {"ok": r.status_code == 200}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    db = get_db_status()
    chroma = get_chroma_status()
    return templates.TemplateResponse("index.html", {
        "request": request,
        "db": db,
        "chroma": chroma,
        "now": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "rss_stats": db.get("rss_stats", []),
        "yt_stats": db.get("yt_stats", []),
    })


@app.get("/api/status")
async def api_status():
    return {
        "db": get_db_status(),
        "chroma": get_chroma_status(),
        "timestamp": datetime.now().isoformat(),
    }

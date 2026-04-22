"""
BrogiASIST — Ingest scheduler
Email:   IMAP IDLE push (jeden thread per účet)
RSS:     každých 30 min (polling)
YouTube: každé 2 hodiny (API kvóta)
"""

import logging
import sys
import os
import time
from datetime import datetime, timezone, timedelta
from apscheduler.schedulers.background import BackgroundScheduler

sys.path.insert(0, os.path.dirname(__file__))

from ingest_email_idle import start_all as start_idle_listeners
from ingest_email import ACCOUNTS, fetch_messages, upsert_messages
from ingest_rss import get_token as rss_token, fetch_items, upsert_articles
from ingest_youtube import get_access_token, get_subscriptions, get_uploads_playlist, get_recent_videos, upsert_videos

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("scheduler")

DAYS_BACK = 7


def job_email_scan():
    """Záložní scan — chytí co IDLE mohl minout (archivace, krátký výpadek)."""
    since = datetime.now(tz=timezone.utc) - timedelta(hours=1)
    total = 0
    for acc in ACCOUNTS:
        try:
            msgs = fetch_messages(acc, since)
            new_c, _ = upsert_messages(msgs)
            total += new_c
        except Exception as e:
            log.error(f"  email scan {acc['name']}: {e}")
    if total:
        log.info(f"EMAIL scan (záloha): zachyceno +{total} nových")


def job_rss():
    log.info("RSS ingest START")
    try:
        token = rss_token()
        items = fetch_items(token)
        new_c, _ = upsert_articles(items)
        log.info(f"RSS ingest DONE — nových: {new_c} z {len(items)}")
    except Exception as e:
        log.error(f"RSS ingest CHYBA: {e}")


def job_youtube():
    log.info("YOUTUBE ingest START")
    try:
        since = datetime.now(tz=timezone.utc) - timedelta(days=DAYS_BACK)
        token = get_access_token()
        subs = get_subscriptions(token)
        all_videos = []
        for sub in subs:
            try:
                pl_id = get_uploads_playlist(sub["channel_id"], token)
                if pl_id:
                    all_videos.extend(get_recent_videos(pl_id, token, since))
            except Exception:
                pass
        new_c, _ = upsert_videos(all_videos)
        log.info(f"YOUTUBE ingest DONE — nových: {new_c} z {len(all_videos)}")
    except Exception as e:
        log.error(f"YOUTUBE ingest CHYBA: {e}")


if __name__ == "__main__":
    log.info("=== BrogiASIST Scheduler START ===")

    # Email — IMAP IDLE push listeners (daemon threads)
    idle_threads = start_idle_listeners()
    log.info(f"Email IDLE listeners: {len(idle_threads)} účtů")

    # RSS + YouTube — APScheduler polling
    scheduler = BackgroundScheduler(timezone="Europe/Prague")
    scheduler.add_job(job_email_scan, "interval", minutes=30, id="email_scan", next_run_time=datetime.now())
    scheduler.add_job(job_rss,        "interval", minutes=30, id="rss",        next_run_time=datetime.now())
    scheduler.add_job(job_youtube,    "interval", hours=2,    id="youtube",    next_run_time=datetime.now())
    scheduler.start()

    log.info("RSS/30min, YouTube/2h — běží")

    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        log.info("Ukončuji scheduler...")
        scheduler.shutdown()

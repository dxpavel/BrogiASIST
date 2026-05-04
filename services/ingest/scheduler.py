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
import threading
from datetime import datetime, timezone, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
import uvicorn

sys.path.insert(0, os.path.dirname(__file__))

from ingest_email_idle import start_all as start_idle_listeners
from api import app as _api_app
from ingest_email import ACCOUNTS, fetch_messages, upsert_messages
from ingest_rss import get_token as rss_token, fetch_items, upsert_articles
from ingest_youtube import get_access_token, get_subscriptions, get_uploads_playlist, get_recent_videos, upsert_videos
from ingest_mantis import fetch_issues as mantis_fetch, upsert_issues as mantis_upsert, PROJECT_IDS
from ingest_omnifocus import ingest_omnifocus
from ingest_apple_apps import ingest_notes, ingest_reminders, ingest_contacts, ingest_calendar
from telegram_callback import run_callback_loop
from classify_emails import classify_new_emails
from notify_emails import notify_classified_emails
from imap_status import job_imap_login_check

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


def job_mantis():
    log.info("MANTIS ingest START")
    since = datetime.now(tz=timezone.utc) - timedelta(days=DAYS_BACK)
    total = 0
    for pid in PROJECT_IDS:
        try:
            issues = mantis_fetch(pid, since)
            new_c, _ = mantis_upsert(issues)
            total += new_c
        except Exception as e:
            log.error(f"  MANTIS projekt {pid}: {e}")
    if total:
        log.info(f"MANTIS ingest DONE — nových/aktualizovaných: {total}")
    else:
        log.info("MANTIS ingest DONE — žádné změny")


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

    # Ingest API (port 9001)
    api_thread = threading.Thread(
        target=lambda: uvicorn.run(_api_app, host="0.0.0.0", port=9001, log_level="warning"),
        daemon=True, name="ingest-api"
    )
    api_thread.start()
    log.info("Ingest API: http://0.0.0.0:9001 START")

    # Telegram callback loop (daemon thread)
    tg_thread = threading.Thread(target=run_callback_loop, daemon=True, name="tg-callback")
    tg_thread.start()
    log.info("Telegram callback loop: START")

    # Email — IMAP IDLE push listeners (daemon threads)
    idle_threads = start_idle_listeners()
    log.info(f"Email IDLE listeners: {len(idle_threads)} účtů")

    # RSS + YouTube — APScheduler polling
    scheduler = BackgroundScheduler(timezone="Europe/Prague")
    scheduler.add_job(job_email_scan,  "interval", minutes=30, id="email_scan",  next_run_time=datetime.now())
    scheduler.add_job(job_rss,         "interval", minutes=30, id="rss",         next_run_time=datetime.now())
    scheduler.add_job(job_mantis,      "interval", minutes=30, id="mantis",      next_run_time=datetime.now())
    scheduler.add_job(job_youtube,     "interval", hours=2,    id="youtube",     next_run_time=datetime.now())
    scheduler.add_job(ingest_omnifocus, "interval", minutes=10, id="omnifocus",  next_run_time=datetime.now())
    now_tz = datetime.now(tz=timezone.utc)
    scheduler.add_job(ingest_notes,     "interval", minutes=30, id="notes",      next_run_time=now_tz)
    scheduler.add_job(ingest_reminders, "interval", minutes=15, id="reminders",  next_run_time=now_tz)
    scheduler.add_job(ingest_contacts,  "interval", hours=12,   id="contacts",   next_run_time=now_tz)
    scheduler.add_job(ingest_calendar,       "interval", minutes=15, id="calendar",  next_run_time=now_tz)
    scheduler.add_job(classify_new_emails,      "interval", minutes=5,  id="classify",  next_run_time=now_tz)
    scheduler.add_job(notify_classified_emails, "interval", minutes=2,  id="notify",    next_run_time=now_tz)
    scheduler.add_job(job_imap_login_check,     "interval", minutes=5,  id="imap_login", next_run_time=now_tz)

    # Pending actions queue worker — drain každou minutu (spec D5).
    # Apple Bridge offline → akce v pending_actions, worker je dorovná.
    from pending_worker import drain_queue
    scheduler.add_job(drain_queue, "interval", minutes=1, id="drain_queue", next_run_time=now_tz)

    scheduler.start()

    log.info("RSS/30min, YouTube/2h, OmniFocus/10min, Notes/30min, Reminders/15min, Contacts/6h, Calendar/15min — běží")

    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        log.info("Ukončuji scheduler...")
        scheduler.shutdown()

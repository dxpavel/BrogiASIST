"""
BrogiASIST — Ingest HTTP API (port 9001)
Umožňuje dashboardu spustit classify + notify + IMAP akce na vyžádání.
"""
import logging
from fastapi import FastAPI
from classify_emails import classify_new_emails
from notify_emails import notify_classified_emails
from imap_actions import mark_read, move_to_trash, move_to_brogi_folder
from telegram_callback import _email_action

log = logging.getLogger("ingest_api")
app = FastAPI(title="BrogiASIST Ingest API", docs_url=None, redoc_url=None)


@app.post("/fetch-now")
def fetch_now():
    try:
        classify_new_emails()
        notify_classified_emails()
        log.info("fetch-now: classify + notify OK")
        return {"status": "ok"}
    except Exception as e:
        log.error(f"fetch-now error: {e}")
        return {"status": "error", "detail": str(e)}


@app.post("/email/{email_id}/mark-read")
def api_mark_read(email_id: str):
    ok = mark_read(email_id)
    return {"ok": ok}


@app.post("/email/{email_id}/move-trash")
def api_move_trash(email_id: str):
    ok = move_to_trash(email_id)
    return {"ok": ok}


@app.post("/email/{email_id}/action/{action}")
def api_email_action(email_id: str, action: str):
    """Spustí TG akci (hotovo, spam, of, rem, note, ceka, precteno, skip) přes dashboard."""
    try:
        _email_action(email_id, action)
        return {"ok": True}
    except Exception as e:
        log.error(f"email action {action} {email_id}: {e}")
        return {"ok": False, "detail": str(e)}


@app.get("/health")
def health():
    return {"status": "ok"}

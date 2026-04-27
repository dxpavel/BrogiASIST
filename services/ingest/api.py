"""
BrogiASIST — Ingest HTTP API (port 9001)
Umožňuje dashboardu spustit classify + notify + IMAP akce na vyžádání.
"""
import logging
from fastapi import FastAPI
from pydantic import BaseModel
from classify_emails import classify_new_emails
from notify_emails import notify_classified_emails
from imap_actions import mark_read, move_to_trash, move_to_brogi_folder
from telegram_callback import _email_action
from chroma_client import find_repeat_action_with_score
from db import get_conn

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


class SuggestedRequest(BaseModel):
    ids: list[str]


@app.post("/emails/suggested")
def api_emails_suggested(req: SuggestedRequest):
    """Batch: pro list email_id vrátí Chroma predikci (find_repeat_action_with_score).

    Vrací: {email_id: {"action": "of", "confidence_pct": 88} | None, ...}
    Použití: dashboard /úkoly route — zvýraznění predikovaného tlačítka.
    """
    out: dict[str, dict | None] = {}
    if not req.ids:
        return out
    try:
        conn = get_conn(); cur = conn.cursor()
        # IN (...) přes mogrify není potřeba — ANY na uuid array.
        cur.execute(
            "SELECT id::text, from_address, subject, body_text "
            "FROM email_messages WHERE id::text = ANY(%s)",
            (req.ids,)
        )
        rows = cur.fetchall()
        cur.close(); conn.close()
        for eid, from_addr, subject, body in rows:
            res = find_repeat_action_with_score(from_addr or "", subject or "", body or "")
            if res:
                action, cnt, total = res
                pct = round(100 * cnt / max(total, 1))
                out[eid] = {"action": action, "confidence_pct": pct}
            else:
                out[eid] = None
    except Exception as e:
        log.error(f"emails/suggested error: {e}")
    return out


@app.get("/health")
def health():
    return {"status": "ok"}

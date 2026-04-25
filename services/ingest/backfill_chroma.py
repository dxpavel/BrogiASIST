"""
BrogiASIST — Backfill ChromaDB email_actions z historických reviewed emailů.

Mapuje DB stav → action:
  task_status='HOTOVO'                       → hotovo
  task_status='→OF'                          → of
  task_status='→REM'                         → rem
  is_spam=TRUE                               → spam
  task_status='ČEKÁ-NA-MĚ'                   → ceka
  folder LIKE 'BrogiASIST/%' (bez task_st)   → precteno

Spuštění (v scheduler kontejneru):
  docker cp services/ingest/backfill_chroma.py brogi_scheduler:/app/
  docker exec brogi_scheduler python backfill_chroma.py

Idempotentní — upsert podle email_id.
"""
import logging
from db import get_conn
from chroma_client import store_email_action

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("backfill_chroma")


def map_action(task_status: str | None, is_spam: bool, folder: str | None) -> str | None:
    if is_spam:
        return "spam"
    ts = (task_status or "").strip()
    if ts == "HOTOVO":
        return "hotovo"
    if ts == "→OF":
        return "of"
    if ts == "→REM":
        return "rem"
    if ts in ("ČEKÁ-NA-MĚ", "ČEKÁ-NA-ODPOVĚĎ"):
        return "ceka"
    if folder and folder.startswith("BrogiASIST/"):
        return "precteno"
    return None


def main():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, from_address, subject, body_text, typ, firma, mailbox,
               ai_confidence, task_status, is_spam, folder, sent_at
        FROM email_messages
        WHERE human_reviewed = TRUE
        ORDER BY sent_at ASC
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    log.info(f"backfill: {len(rows)} reviewed emailů")
    inserted = 0
    skipped = 0
    for r in rows:
        (eid, from_addr, subject, body, typ, firma, mailbox,
         ai_conf, task_st, is_spam, folder, sent_at) = r
        action = map_action(task_st, is_spam, folder)
        if not action:
            skipped += 1
            continue
        ts = sent_at.isoformat() if sent_at else ""
        store_email_action(
            str(eid), from_addr or "", subject or "", body or "",
            action, typ or "", firma or "", mailbox or "",
            ai_confidence=ai_conf,
            task_status=task_st or "",
            timestamp=ts,
            human_corrected=True,
        )
        inserted += 1

    log.info(f"backfill done: inserted={inserted} skipped={skipped}")


if __name__ == "__main__":
    main()

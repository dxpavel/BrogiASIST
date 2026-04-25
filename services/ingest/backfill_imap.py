"""
BrogiASIST — jednorázový backfill IMAP akcí
Projde všechny reviewed/spam emaily v DB, najde je v IMAP přes Message-ID
a provede zpětně: mark_read + přesun do správné složky.
"""
import logging
import imaplib
from collections import defaultdict
from db import get_conn
from ingest_email import ACCOUNTS, connect

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("backfill")

TRASH_MAP = {
    "imap.gmail.com":   "[Gmail]/Trash",
    "imap.mail.me.com": "Deleted Messages",
}
BROGI_HOTOVO = "BrogiASIST/HOTOVO"


def _account(mailbox: str) -> dict | None:
    for acc in ACCOUNTS:
        if acc["name"] == mailbox:
            return acc
    return None


def _uid_by_message_id(m: imaplib.IMAP4, message_id: str) -> str | None:
    """Hledá email v aktuálně vybrané složce podle Message-ID."""
    clean = message_id.strip().strip("<>")
    # Zkus s lomítky i bez
    for mid in [f"<{clean}>", clean]:
        try:
            typ, data = m.uid("SEARCH", None, f'HEADER Message-ID "{mid}"')
            if typ == "OK" and data[0]:
                uids = data[0].split()
                if uids:
                    return uids[-1].decode()
        except Exception:
            pass
    return None


def _ensure_folder(m: imaplib.IMAP4, folder: str):
    try:
        m.create(folder)
    except Exception:
        pass


def _move_uid(m: imaplib.IMAP4, uid: str, dest: str):
    res = m.uid("MOVE", uid, dest)
    if res[0] != "OK":
        m.uid("COPY", uid, dest)
        m.uid("STORE", uid, "+FLAGS", "\\Deleted")
        m.expunge()


def process_mailbox(acc: dict, emails: list):
    name = acc["name"]
    log.info(f"[{name}] Zpracovávám {len(emails)} emailů")
    try:
        m = connect(acc)
    except Exception as e:
        log.error(f"[{name}] Připojení selhalo: {e}")
        return

    done = 0
    skip = 0

    for row in emails:
        email_id, source_id, is_spam, task_status, folder_db = row
        if not source_id or source_id.startswith("uid-"):
            log.warning(f"  [{email_id}] Bez platného Message-ID, přeskakuji")
            skip += 1
            continue

        # Hledej v INBOX i ve stávající složce
        found_uid = None
        for search_folder in ["INBOX", folder_db or "INBOX"]:
            try:
                m.select(search_folder)
                found_uid = _uid_by_message_id(m, source_id)
                if found_uid:
                    break
            except Exception:
                pass

        if not found_uid:
            log.debug(f"  [{email_id}] Nenalezen v IMAP (možná už přesunut)")
            skip += 1
            continue

        try:
            if is_spam:
                trash = TRASH_MAP.get(acc["host"], "Trash")
                _move_uid(m, found_uid, trash)
                log.info(f"  [{email_id}] → Trash (spam)")
            else:
                _ensure_folder(m, BROGI_HOTOVO)
                _move_uid(m, found_uid, BROGI_HOTOVO)
                log.info(f"  [{email_id}] → {BROGI_HOTOVO}")
            done += 1
        except Exception as e:
            log.error(f"  [{email_id}] Akce selhala: {e}")
            skip += 1

    try:
        m.logout()
    except Exception:
        pass

    log.info(f"[{name}] Hotovo: {done} provedeno, {skip} přeskočeno")


def main():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, source_id, is_spam, task_status, folder
        FROM email_messages
        WHERE (human_reviewed = TRUE OR is_spam = TRUE)
          AND status IN ('reviewed', 'unsubscribed')
        ORDER BY mailbox, sent_at
    """)
    rows = cur.fetchall()

    # Potřebujeme mailbox — načteme zvlášť
    cur.execute("""
        SELECT id, mailbox, source_id, is_spam, task_status, folder
        FROM email_messages
        WHERE (human_reviewed = TRUE OR is_spam = TRUE)
          AND status IN ('reviewed', 'unsubscribed')
        ORDER BY mailbox, sent_at
    """)
    rows = cur.fetchall()
    cur.close()
    conn.close()

    by_mailbox = defaultdict(list)
    for email_id, mailbox, source_id, is_spam, task_status, folder in rows:
        by_mailbox[mailbox].append((email_id, source_id, is_spam, task_status, folder))

    log.info(f"Celkem {len(rows)} emailů v {len(by_mailbox)} mailboxech")

    for mailbox, emails in by_mailbox.items():
        acc = _account(mailbox)
        if not acc:
            log.warning(f"[{mailbox}] Účet nenalezen v ACCOUNTS, přeskakuji")
            continue
        if not acc.get("supports_idle", True) is False:
            pass  # i seznamový účet zkusíme
        process_mailbox(acc, emails)

    log.info("=== Backfill dokončen ===")


if __name__ == "__main__":
    main()

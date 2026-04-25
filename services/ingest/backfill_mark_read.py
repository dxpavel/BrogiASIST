"""
BrogiASIST — backfill: označ reviewed emaily jako přečtené v IMAP
Hledá emaily v IMAP přes Message-ID, mark as \Seen + přesune do BrogiASIST/HOTOVO
(nebo složky dle task_status). Skip = zůstane v INBOX unread.
"""
import logging
import imaplib
from collections import defaultdict
from db import get_conn
from ingest_email import ACCOUNTS, connect

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("backfill_read")

TRASH_MAP = {
    "imap.gmail.com":   "[Gmail]/Trash",
    "imap.mail.me.com": "Deleted Messages",
}

# Mapování task_status → složka
STATUS_FOLDER = {
    "→OF":            "HOTOVO",
    "→REM":           "HOTOVO",
    "HOTOVO":         "HOTOVO",
    "ČEKÁ-NA-MĚ":     "CEKA",
    "ČEKÁ-NA-ODPOVĚĎ":"CEKA",
    None:             "HOTOVO",
    "":               "HOTOVO",
}

# Mapování typ → složka (fallback)
TYP_FOLDER = {
    "NOTIFIKACE": "NOTIFIKACE",
    "NEWSLETTER": "NEWSLETTER",
    "ESHOP":      "ESHOP",
}

SEARCH_FOLDERS = ["INBOX", "BrogiASIST/HOTOVO", "BrogiASIST/NEWSLETTER",
                  "BrogiASIST/NOTIFIKACE", "BrogiASIST/CEKA"]


def _account(mailbox: str) -> dict | None:
    for acc in ACCOUNTS:
        if acc["name"] == mailbox:
            return acc
    return None


def _uid_by_message_id(m: imaplib.IMAP4, message_id: str) -> str | None:
    clean = message_id.strip().strip("<>")
    for mid in [f"<{clean}>", clean]:
        try:
            # Separate args form — funguje na Gmail, iCloud i Forpsi
            typ, data = m.uid("SEARCH", None, "HEADER", "Message-ID", mid)
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


def _uid_move(m: imaplib.IMAP4, uid: str, dest: str):
    res = m.uid("MOVE", uid, dest)
    if res[0] != "OK":
        m.uid("COPY", uid, dest)
        m.uid("STORE", uid, "+FLAGS", "\\Deleted")
        m.expunge()


def _update_db(conn, email_id, folder: str):
    cur = conn.cursor()
    cur.execute(
        "UPDATE email_messages SET folder=%s WHERE id=%s",
        (folder, email_id)
    )
    conn.commit()
    cur.close()


def _process_single(acc: dict, email_id: str, source_id: str, task_status: str, typ: str,
                     folder_db: str, db_conn) -> str:
    """Zpracuje jeden email — fresh IMAP spojení pro každý email. Vrací 'done'/'already'/'skip'."""
    try:
        m = connect(acc)
    except Exception as e:
        log.error(f"  [{email_id[:8]}] Připojení: {e}")
        return "skip"

    found_uid = None
    found_folder = None
    search_list = [folder_db or "INBOX"] + [f for f in SEARCH_FOLDERS if f != (folder_db or "INBOX")]

    for sf in search_list:
        try:
            res = m.select(sf)
            if res[0] != "OK":
                continue
            uid = _uid_by_message_id(m, source_id)
            if uid:
                found_uid = uid
                found_folder = sf
                break
        except Exception:
            continue

    if not found_uid:
        try:
            m.logout()
        except Exception:
            pass
        return "skip"

    dest_sub = STATUS_FOLDER.get(task_status, None) or TYP_FOLDER.get(typ, "HOTOVO")
    dest = f"BrogiASIST/{dest_sub}"

    result = "skip"
    try:
        m.select(found_folder)
        m.uid("STORE", found_uid, "+FLAGS", "(\\Seen)")
        if found_folder != dest:
            _ensure_folder(m, dest)
            _uid_move(m, found_uid, dest)
            _update_db(db_conn, email_id, dest)
            log.info(f"  [{email_id[:8]}] {found_folder} → {dest}")
            result = "done"
        else:
            log.info(f"  [{email_id[:8]}] Již v {dest}, jen mark read")
            result = "already"
    except Exception as e:
        log.error(f"  [{email_id[:8]}] Akce selhala: {e}")

    try:
        m.logout()
    except Exception:
        pass
    return result


def process_mailbox(acc: dict, emails: list, db_conn):
    name = acc["name"]
    log.info(f"[{name}] {len(emails)} emailů ke zpracování")

    done = already = skip = 0

    for email_id, source_id, task_status, typ, folder_db in emails:
        if not source_id or source_id.startswith("uid-"):
            log.warning(f"  [{email_id[:8]}] Bez Message-ID, skip")
            skip += 1
            continue
        r = _process_single(acc, email_id, source_id, task_status, typ, folder_db, db_conn)
        if r == "done":
            done += 1
        elif r == "already":
            done += 1
            already += 1
        else:
            skip += 1

    log.info(f"[{name}] ✅ {done} zpracováno ({already} jen mark-read), {skip} přeskočeno")


def main():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, source_id, task_status, typ, folder, mailbox
        FROM email_messages
        WHERE human_reviewed = TRUE AND is_spam = FALSE
        ORDER BY mailbox, sent_at
    """)
    rows = cur.fetchall()
    cur.close()

    by_mailbox = defaultdict(list)
    for email_id, source_id, task_status, typ, folder, mailbox in rows:
        by_mailbox[mailbox].append((email_id, source_id, task_status, typ, folder))

    log.info(f"Celkem {len(rows)} emailů v {len(by_mailbox)} mailboxech")

    for mailbox, emails in by_mailbox.items():
        acc = _account(mailbox)
        if not acc:
            log.warning(f"[{mailbox}] Účet nenalezen, skip")
            continue
        process_mailbox(acc, emails, conn)

    conn.close()
    log.info("=== Backfill dokončen ===")


if __name__ == "__main__":
    main()

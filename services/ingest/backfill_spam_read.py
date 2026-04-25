"""
BrogiASIST — backfill spam: přesuň do Trash všechny auto-spam emaily.
Strategie: 1) zkus UID v uloženém folderu, 2) fallback Message-ID search v All Mail / INBOX.
"""
import logging
from collections import defaultdict
from db import get_conn
from ingest_email import ACCOUNTS, connect

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("backfill_spam")

TRASH_MAP = {
    "imap.gmail.com":       "[Gmail]/Trash",
    "imap.mail.me.com":     "Deleted Messages",
    "imap.forpsi.com":      "INBOX.Trash",
    "mail.dxpsolutions.cz": "Trash",
    "imap.seznam.cz":       "Trash",
}

# Kde hledat přes Message-ID (pro každý host)
SEARCH_FOLDERS_MAP = {
    "imap.gmail.com":       ["INBOX", "[Gmail]/All Mail", "[Gmail]/Promotions", "[Gmail]/Social"],
    "imap.mail.me.com":     ["INBOX", "BrogiASIST/HOTOVO", "BrogiASIST/NEWSLETTER", "BrogiASIST/NOTIFIKACE"],
    "imap.forpsi.com":      ["INBOX", "INBOX.Archive"],
    "mail.dxpsolutions.cz": ["INBOX", "Archive"],
}


def _account(mailbox: str) -> dict | None:
    for acc in ACCOUNTS:
        if acc["name"] == mailbox:
            return acc
    return None


def _imap_folder(name: str) -> str:
    """Obalí jméno složky uvozovkami pokud obsahuje mezery."""
    if " " in name and not name.startswith('"'):
        return f'"{name}"'
    return name


def _uid_move(m, uid: str, dest: str):
    d = _imap_folder(dest)
    res = m.uid("MOVE", uid, d)
    if res[0] != "OK":
        m.uid("COPY", uid, d)
        m.uid("STORE", uid, "+FLAGS", "(\\Seen \\Deleted)")
        m.expunge()


def _find_by_uid(m, imap_uid: int, folder: str) -> str | None:
    """Vrátí UID string pokud existuje v daném folderu, jinak None."""
    try:
        res = m.select(folder)
        if res[0] != "OK":
            return None
        typ, data = m.uid("FETCH", str(imap_uid), "(FLAGS)")
        if data and data[0]:
            return str(imap_uid)
    except Exception:
        pass
    return None


def _find_by_message_id(m, source_id: str, host: str) -> tuple[str | None, str | None]:
    """Vrátí (uid, folder) pokud nalezeno přes Message-ID, jinak (None, None)."""
    if not source_id or source_id.startswith("uid-"):
        return None, None
    folders = SEARCH_FOLDERS_MAP.get(host, ["INBOX"])
    clean = source_id.strip().strip("<>")
    for sf in folders:
        try:
            res = m.select(sf)
            if res[0] != "OK":
                continue
            for mid in [f"<{clean}>", clean]:
                typ, data = m.uid("SEARCH", None, "HEADER", "Message-ID", mid)
                if typ == "OK" and data[0]:
                    uids = data[0].split()
                    if uids:
                        return uids[-1].decode(), sf
        except Exception:
            continue
    return None, None


def process_single(acc: dict, email_id, imap_uid, source_id: str, folder_db: str, trash: str, db_conn):
    host = acc["host"]
    try:
        m = connect(acc)
    except Exception as e:
        log.error(f"  [{str(email_id)[:8]}] Připojení: {e}")
        return False

    found_uid = None
    found_folder = None

    # 1. Zkus přímý UID
    if imap_uid:
        found_uid = _find_by_uid(m, imap_uid, folder_db or "INBOX")
        if found_uid:
            found_folder = folder_db or "INBOX"

    # 2. Fallback: hledej Message-ID
    if not found_uid and source_id:
        found_uid, found_folder = _find_by_message_id(m, source_id, host)

    if not found_uid:
        try:
            m.logout()
        except Exception:
            pass
        return False

    # Přesuň do Trash
    try:
        m.select(found_folder)
        _uid_move(m, found_uid, trash)
        m.logout()
    except Exception as e:
        log.error(f"  [{str(email_id)[:8]}] Move selhalo: {e}")
        try:
            m.logout()
        except Exception:
            pass
        return False

    cur = db_conn.cursor()
    cur.execute(
        "UPDATE email_messages SET folder=%s, status='reviewed', human_reviewed=TRUE WHERE id=%s",
        (trash, email_id)
    )
    db_conn.commit()
    cur.close()

    log.info(f"  [{str(email_id)[:8]}] {found_folder} → {trash}")
    return True


def process_mailbox(acc: dict, emails: list, db_conn):
    name = acc["name"]
    host = acc["host"]
    trash = TRASH_MAP.get(host, "Trash")
    log.info(f"[{name}] {len(emails)} spam emailů, Trash={trash}")

    done = skip = 0
    for email_id, imap_uid, source_id, folder_db in emails:
        ok = process_single(acc, email_id, imap_uid, source_id or "", folder_db or "INBOX", trash, db_conn)
        if ok:
            done += 1
        else:
            log.debug(f"  [{str(email_id)[:8]}] Nenalezen, přeskakuji")
            skip += 1

    log.info(f"[{name}] ✅ {done} přesunuto, {skip} přeskočeno")


def main():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, imap_uid, source_id, folder, mailbox
        FROM email_messages
        WHERE is_spam = TRUE
          AND status NOT IN ('reviewed', 'unsubscribed')
        ORDER BY mailbox, sent_at
    """)
    rows = cur.fetchall()
    cur.close()

    by_mailbox = defaultdict(list)
    for email_id, imap_uid, source_id, folder, mailbox in rows:
        by_mailbox[mailbox].append((email_id, imap_uid, source_id, folder))

    log.info(f"Celkem {len(rows)} spam emailů v {len(by_mailbox)} mailboxech")

    for mailbox, emails in by_mailbox.items():
        acc = _account(mailbox)
        if not acc:
            log.warning(f"[{mailbox}] Účet nenalezen")
            continue
        process_mailbox(acc, emails, conn)

    conn.close()
    log.info("=== Backfill spam dokončen ===")


if __name__ == "__main__":
    main()

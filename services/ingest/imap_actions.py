"""
BrogiASIST — IMAP akce
mark_read, move_to_trash, move_to_folder
Volá se VŽDY po provedení akce (auto / TG / WebUI).
"""
import logging
import imaplib
from db import get_conn
from ingest_email import ACCOUNTS, connect

log = logging.getLogger(__name__)

# Trash složky dle IMAP hostu
TRASH_MAP = {
    "imap.gmail.com":      "[Gmail]/Trash",
    "imap.mail.me.com":    "Deleted Messages",
    "imap.forpsi.com":     "INBOX.Trash",
    "mail.dxpsolutions.cz": "Trash",
    "imap.seznam.cz":      "Trash",
}

BROGI_PREFIX = "BrogiASIST"

# Mapování typ emailu → složka
TYP_FOLDER = {
    "NOTIFIKACE": "NOTIFIKACE",
    "ESHOP":      "ESHOP",
    "NEWSLETTER": "NEWSLETTER",
    "FAKTURA":    "FAKTURA",
    "POTVRZENÍ":  "POTVRZENI",
    "NABÍDKA":    "NABIDKA",
    "ÚKOL":       "TODO",
    "INFO":       "INFO",
    "POZVÁNKA":   "POZVANKA",
}


def _account(mailbox: str) -> dict | None:
    for acc in ACCOUNTS:
        if acc["name"] == mailbox:
            return acc
    return None


def _imap_connect_inbox(acc: dict, readonly: bool = False):
    m = connect(acc)
    m.select("INBOX", readonly=readonly)
    return m


def _imap_folder(name: str) -> str:
    if " " in name and not name.startswith('"'):
        return f'"{name}"'
    return name


def _uid_move(m: imaplib.IMAP4, uid: str, dest: str):
    """Přesune zprávu do dest. Fallback na COPY+DELETE pokud MOVE není podporováno."""
    d = _imap_folder(dest)
    res = m.uid("MOVE", uid, d)
    if res[0] != "OK":
        m.uid("COPY", uid, d)
        m.uid("STORE", uid, "+FLAGS", "\\Deleted")
        m.expunge()


def _ensure_folder(m: imaplib.IMAP4, folder: str):
    """Vytvoří IMAP složku pokud neexistuje."""
    m.create(folder)  # většina serverů vrátí OK i pokud existuje


def _update_db_folder(email_id, folder: str, mark_read: bool = True):
    conn = get_conn()
    cur = conn.cursor()
    if mark_read:
        cur.execute(
            "UPDATE email_messages SET folder=%s, status='reviewed', human_reviewed=TRUE WHERE id=%s",
            (folder, email_id)
        )
    else:
        cur.execute("UPDATE email_messages SET folder=%s WHERE id=%s", (folder, email_id))
    conn.commit()
    cur.close()
    conn.close()


def get_imap_info(email_id) -> tuple | None:
    """Vrátí (mailbox, imap_uid, folder) pro daný email."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT mailbox, imap_uid, folder FROM email_messages WHERE id=%s", (email_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row  # (mailbox, imap_uid, folder) nebo None


def mark_read(email_id) -> bool:
    """Označí email jako přečtený na IMAP serveru."""
    info = get_imap_info(email_id)
    if not info:
        return False
    mailbox, imap_uid, folder = info
    if not imap_uid:
        return False
    acc = _account(mailbox)
    if not acc:
        return False
    try:
        m = connect(acc)
        imap_folder = folder or "INBOX"
        m.select(imap_folder)
        m.uid("STORE", str(imap_uid), "+FLAGS", "(\\Seen)")
        m.logout()
        log.info(f"mark_read OK: {mailbox} uid={imap_uid}")
        return True
    except Exception as e:
        log.error(f"mark_read {mailbox} uid={imap_uid}: {e}")
        return False


def move_to_trash(email_id) -> bool:
    """Přesune email do Trash (spam)."""
    info = get_imap_info(email_id)
    if not info:
        return False
    mailbox, imap_uid, folder = info
    if not imap_uid:
        return False
    acc = _account(mailbox)
    if not acc:
        return False
    trash = TRASH_MAP.get(acc["host"], "Trash")
    try:
        m = connect(acc)
        m.select(folder or "INBOX")
        _uid_move(m, str(imap_uid), trash)
        m.logout()
        _update_db_folder(email_id, trash, mark_read=True)
        log.info(f"move_to_trash OK: {mailbox} uid={imap_uid} → {trash}")
        return True
    except Exception as e:
        log.error(f"move_to_trash {mailbox} uid={imap_uid}: {e}")
        return False


def move_to_brogi_folder(email_id, subfolder: str) -> bool:
    """Přesune email do BrogiASIST/{subfolder}."""
    info = get_imap_info(email_id)
    if not info:
        return False
    mailbox, imap_uid, folder = info
    if not imap_uid:
        return False
    acc = _account(mailbox)
    if not acc:
        return False
    dest = f"{BROGI_PREFIX}/{subfolder}"
    try:
        m = connect(acc)
        _ensure_folder(m, dest)
        m.select(folder or "INBOX")
        _uid_move(m, str(imap_uid), dest)
        m.logout()
        _update_db_folder(email_id, dest, mark_read=True)
        log.info(f"move_to_brogi OK: {mailbox} uid={imap_uid} → {dest}")
        return True
    except Exception as e:
        log.error(f"move_to_brogi {mailbox} uid={imap_uid} → {dest}: {e}")
        return False


def action_done(email_id):
    """Zavolat po každé akci — mark_read na IMAP."""
    mark_read(email_id)

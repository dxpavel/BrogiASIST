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

# BUG-004 fix: Forpsi + Synology Cyrus IMAP používají strukturu
# `INBOX.foo.bar` místo `foo/bar`. Per-host mapping (sjednocené s
# ensure_brogi_folders.py).
DOTTED_HOSTS = {"imap.forpsi.com", "mail.dxpsolutions.cz"}


def _brogi_path(host: str, subfolder: str) -> str:
    """Vrátí správný IMAP folder path pro BrogiASIST hierarchii dle hostu."""
    if host in DOTTED_HOSTS:
        return f"INBOX.BrogiASIST.{subfolder}"
    return f"BrogiASIST/{subfolder}"


def _folder_exists(m: imaplib.IMAP4, folder: str) -> bool:
    """BUG-004/005 pre-flight: ověří že IMAP složka existuje (m.list pattern)."""
    try:
        typ, raw = m.list(pattern=folder)
    except Exception:
        # Některé servery nepodporují pattern arg — zkus celý list
        typ, raw = m.list()
    if typ != "OK" or not raw:
        return False
    target = folder.strip().strip('"')
    for line in raw:
        s = line.decode() if isinstance(line, bytes) else line
        try:
            name = s.rsplit(" ", 1)[-1].strip().strip('"')
            if name == target:
                return True
        except Exception:
            continue
    return False


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
    """Přesune zprávu do dest. Fallback na COPY+DELETE pokud MOVE není podporováno.

    BUG-005 fix: pokud MOVE i COPY selžou (např. cíl neexistuje), vyhazuje
    RuntimeError místo silent fail. Volající nesmí poté psát do DB folder.
    """
    d = _imap_folder(dest)
    res = m.uid("MOVE", uid, d)
    if res[0] == "OK":
        return
    # Fallback COPY + STORE \Deleted + EXPUNGE
    res_c = m.uid("COPY", uid, d)
    if res_c[0] != "OK":
        raise RuntimeError(f"_uid_move failed: MOVE+COPY oba selhaly pro dest={dest} (response={res_c})")
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
        typ, _ = m.select(imap_folder)
        if typ != "OK":
            m.logout()
            log.warning(f"mark_read skip: SELECT {imap_folder} returned {typ} ({mailbox} uid={imap_uid})")
            return False
        m.uid("STORE", str(imap_uid), "+FLAGS", "(\\Seen)")
        m.logout()
        log.info(f"mark_read OK: {mailbox} uid={imap_uid}")
        return True
    except Exception as e:
        log.error(f"mark_read {mailbox} uid={imap_uid}: {e}")
        return False


def move_to_trash(email_id) -> bool:
    """Přesune email do Trash (spam).

    BUG-005 fix: _uid_move raise při fail → DB se neupdatuje pokud Trash
    neexistuje nebo MOVE/COPY selže.
    """
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
    """Přesune email do BrogiASIST hierarchie.

    BUG-004 fix: per-host folder syntax (Forpsi/Synology Cyrus → INBOX.BrogiASIST.X,
    Gmail/iCloud → BrogiASIST/X) místo hardcoded slash.
    BUG-005 fix: pre-flight check existence + _uid_move raise při fail →
    pokud cíl neexistuje (i po _ensure_folder), DB se NEUPDATUJE → DB nelže.
    """
    info = get_imap_info(email_id)
    if not info:
        return False
    mailbox, imap_uid, folder = info
    if not imap_uid:
        return False
    acc = _account(mailbox)
    if not acc:
        return False
    host = acc.get("host", "")
    # Speciální případ: undo vrací email do INBOX → bez prefixu
    if subfolder == "INBOX":
        dest = "INBOX"
    else:
        dest = _brogi_path(host, subfolder)
    try:
        m = connect(acc)
        # BUG-004: ensure + verify
        if dest != "INBOX":
            _ensure_folder(m, dest)
            if not _folder_exists(m, dest):
                m.logout()
                log.error(f"move_to_brogi REFUSED: dest {dest!r} neexistuje na {host} ani po _ensure_folder ({mailbox} uid={imap_uid})")
                return False
        m.select(folder or "INBOX")
        # BUG-005: _uid_move raise při fail → DB se NEUPDATUJE
        _uid_move(m, str(imap_uid), dest)
        m.logout()
        _update_db_folder(email_id, dest, mark_read=True)
        log.info(f"move_to_brogi OK: {mailbox} uid={imap_uid} → {dest}")
        return True
    except Exception as e:
        log.error(f"move_to_brogi {mailbox} uid={imap_uid} → {dest}: {e}")
        return False


def action_done(email_id):
    """Zavolat po každé akci — mark_read na IMAP.

    BUG-014: Po move_to_trash/move_to_brogi_folder má email v cílové složce
    jiný UID (UIDVALIDITY se mění mezi folders). Pro Trash/Deleted/Spam
    skip — `_update_db_folder` už nastavil is_read=TRUE a STORE by selhal.
    """
    info = get_imap_info(email_id)
    if not info:
        return
    _, _, folder = info
    if folder and any(t in folder.lower() for t in ("trash", "deleted", "spam", "junk")):
        return
    mark_read(email_id)

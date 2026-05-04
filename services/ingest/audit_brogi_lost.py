"""
BrogiASIST — BUG-006 audit: ověř existenci 'BrogiASIST/*' emailů na IMAPu

Pro každý email v DB s folder='BrogiASIST/*' a mailbox z Forpsi/Synology:
1. připoj se na IMAP účet
2. SEARCH HEADER Message-ID napříč všemi BrogiASIST/* a INBOX folders
3. pokud najde → emaily existují (po BUG-004 fix přes ensure_brogi_folders)
   → log INFO, žádná akce
4. pokud nenajde → flag imap_lost=TRUE v DB, log WARNING

Spuštění:
  docker exec brogiasist-scheduler python /app/audit_brogi_lost.py

Idempotentní: lze spustit opakovaně, jen flagne nové suspektní řádky.
"""
import sys
import logging

sys.path.insert(0, "/app")

from db import get_conn
from ingest_email import ACCOUNTS, connect
from imap_actions import _account, DOTTED_HOSTS, _imap_folder

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("audit")


SUSPECT_MAILBOXES = (
    "pavel@dxpsolutions.cz",
    "postapro@dxpavel.cz",
    "support@dxpsolutions.cz",
    "brogi@dxpsolutions.cz",
    "servicedesk@dxpsolutions.cz",
)


def list_brogi_folders(m, host: str) -> list[str]:
    """Vrátí všechny existující BrogiASIST/INBOX subfolders na účtu."""
    typ, raw = m.list()
    if typ != "OK":
        return []
    out = []
    for line in raw or []:
        s = line.decode() if isinstance(line, bytes) else line
        try:
            name = s.rsplit(" ", 1)[-1].strip().strip('"')
        except Exception:
            continue
        if not name:
            continue
        # Forpsi/Synology Cyrus → INBOX.* hierarchie
        # Gmail/iCloud/Seznam → / hierarchie
        if host in DOTTED_HOSTS:
            if name.startswith("INBOX."):
                out.append(name)
        else:
            out.append(name)
    return out


def search_message_id(m, folder: str, message_id: str) -> bool:
    try:
        typ_s, _ = m.select(_imap_folder(folder), readonly=True)
        if typ_s != "OK":
            return False
        # IMAP SEARCH HEADER Message-ID — některé servery neslyšují quotes
        for q in (f'(HEADER Message-ID "{message_id}")', f'HEADER Message-ID {message_id}'):
            typ, data = m.uid("SEARCH", None, q)
            if typ == "OK" and data and data[0]:
                return True
    except Exception as e:
        log.debug(f"search {folder!r}: {e}")
    return False


def audit_account(mailbox: str):
    log.info(f"=== {mailbox} ===")
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, message_id, folder, subject
        FROM email_messages
        WHERE folder LIKE 'BrogiASIST/%'
          AND mailbox = %s
          AND imap_lost = FALSE
        ORDER BY ingested_at
    """, (mailbox,))
    rows = cur.fetchall()
    cur.close()
    conn.close()

    if not rows:
        log.info(f"  {mailbox}: žádné suspektní řádky")
        return

    acc = _account(mailbox)
    if not acc:
        log.warning(f"  {mailbox}: account není v ACCOUNTS — skip")
        return

    host = acc.get("host", "")

    try:
        m = connect(acc)
    except Exception as e:
        log.error(f"  {mailbox}: connect selhal: {e}")
        return

    folders = list_brogi_folders(m, host)
    log.info(f"  {mailbox} ({host}): {len(rows)} suspektních, {len(folders)} dostupných folderů")

    found = 0
    lost = 0
    no_msgid = 0

    for email_id, message_id, db_folder, subject in rows:
        subject_short = (subject or "")[:60]
        if not message_id:
            log.warning(f"  ?  no message_id: id={email_id} folder={db_folder!r} {subject_short!r}")
            no_msgid += 1
            continue

        # Hledej napříč všemi folders
        hit_folder = None
        for folder in folders:
            if search_message_id(m, folder, message_id):
                hit_folder = folder
                break

        if hit_folder:
            log.info(f"  ✓ FOUND in {hit_folder!r}: id={email_id} {subject_short!r}")
            found += 1
            # Update DB folder na reálnou hodnotu (jinou než hardcoded 'BrogiASIST/*')
            try:
                conn = get_conn(); cur = conn.cursor()
                cur.execute("UPDATE email_messages SET folder=%s WHERE id=%s", (hit_folder, email_id))
                conn.commit(); cur.close(); conn.close()
            except Exception as e:
                log.error(f"     DB update failed: {e}")
        else:
            log.warning(f"  ✗ LOST: id={email_id} folder={db_folder!r} {subject_short!r}")
            lost += 1
            try:
                conn = get_conn(); cur = conn.cursor()
                cur.execute("UPDATE email_messages SET imap_lost=TRUE WHERE id=%s", (email_id,))
                conn.commit(); cur.close(); conn.close()
            except Exception as e:
                log.error(f"     DB flag failed: {e}")

    try:
        m.logout()
    except Exception:
        pass

    log.info(f"  {mailbox}: found={found} lost={lost} no_msgid={no_msgid}")


def main():
    log.info("BUG-006 audit START")
    for mailbox in SUSPECT_MAILBOXES:
        try:
            audit_account(mailbox)
        except Exception as e:
            log.error(f"{mailbox} audit failed: {e}")
    log.info("BUG-006 audit DONE")


if __name__ == "__main__":
    main()

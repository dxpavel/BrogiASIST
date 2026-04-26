"""
BrogiASIST — Backfill attachments
=================================

Účel:
  Pro emaily kde `has_attachments=TRUE AND is_spam=FALSE` a v `attachments` jsou
  0 řádků: re-fetch zprávu z IMAP, extrahovat přílohy, uložit na disk + do DB.

Důvod existence:
  BUG-002 v `ingest_email.upsert_messages` — přílohy se ukládaly jen pro nové
  emaily (`is_new=True`). Duplicitní emaily (ON CONFLICT) přílohy nikdy
  nedostaly. Skript opravuje historický datový dluh.

Použití:
  docker cp services/ingest/backfill_attachments.py brogi_scheduler:/app/
  docker exec brogi_scheduler python /app/backfill_attachments.py
  # nebo s limitem:
  docker exec brogi_scheduler python /app/backfill_attachments.py --limit 5

Strategie hledání zprávy:
  1. UID v aktuálním folderu (z DB) — pokud `imap_uid` existuje
  2. Message-ID search v aktuálním folderu (BrogiASIST/HOTOVO atd.)
  3. Message-ID search v INBOX
  4. Per-host fallback: pro Gmail i `[Gmail]/All Mail`
"""
import argparse
import logging
import os
import sys
from db import get_conn
from ingest_email import (
    ACCOUNTS,
    connect,
    decode_header_value,
    _extract_attachments,
    _save_email_attachments,
)
import email as email_mod

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("backfill_att")


# Per-host folder syntax adjustments (lesson #1 — Forpsi má INBOX. prefix)
def _adjust_folder_for_host(folder: str, host: str) -> str:
    """Převede folder z DB tvaru na host-specific syntaxi.

    Forpsi: 'BrogiASIST/HOTOVO' → 'INBOX.BrogiASIST.HOTOVO'
    Ostatní: ponechat.
    """
    if not folder or folder == "INBOX":
        return "INBOX"
    if host == "imap.forpsi.com" and not folder.startswith("INBOX"):
        return "INBOX." + folder.replace("/", ".")
    return folder


def _imap_select_safe(m, folder: str) -> bool:
    """SELECT s uvozovkami pro folder s mezerou nebo lomítkem."""
    fld = folder
    if (" " in fld or "/" in fld) and not fld.startswith('"'):
        fld = f'"{fld}"'
    res, _ = m.select(fld)
    return res == "OK"


def _search_message_id(m, message_id: str) -> str | None:
    """Najde UID zprávy přes Message-ID. Vrací první match jako string nebo None."""
    if not message_id:
        return None
    mid = message_id.strip()
    # iCloud vyžaduje separate args (lesson #1)
    try:
        typ, data = m.uid("SEARCH", None, "HEADER", "Message-ID", mid)
        if typ == "OK" and data and data[0]:
            uids = data[0].split()
            if uids:
                u = uids[0]
                return u.decode() if isinstance(u, bytes) else u
    except Exception as e:
        log.debug(f"Message-ID search exception: {e}")
    return None


def _fetch_raw_by_uid(m, uid: str, account: dict) -> bytes | None:
    """Stáhne raw zprávu podle UID. iCloud vyžaduje BODY[] místo RFC822 (lesson #1)."""
    fetch_cmd = "(BODY[])" if account.get("fetch_cmd") == "BODY[]" else "(RFC822)"
    try:
        typ, raw = m.uid("FETCH", uid, fetch_cmd)
        if typ != "OK":
            return None
        for item in raw:
            if isinstance(item, tuple):
                return item[1]
    except Exception as e:
        log.debug(f"FETCH exception uid={uid}: {e}")
    return None


def _account_for(mailbox: str) -> dict | None:
    for acc in ACCOUNTS:
        if acc["name"] == mailbox:
            return acc
    return None


def _candidate_folders(folder_db: str, host: str) -> list[str]:
    """Pořadí složek k prohledání."""
    out = []
    if folder_db:
        out.append(_adjust_folder_for_host(folder_db, host))
    # Vždy zkusit INBOX
    if "INBOX" not in out:
        out.append("INBOX")
    # Gmail extra
    if host == "imap.gmail.com":
        out.append("[Gmail]/All Mail")
    return out


def find_message(m, message_id: str, imap_uid_db, folders: list[str]) -> tuple[bytes, str, str] | None:
    """Vrátí (raw_bytes, folder_used, uid_used) nebo None."""
    # 1) UID v prvním (z DB) folderu, pokud máme UID
    if imap_uid_db and folders:
        first = folders[0]
        if _imap_select_safe(m, first):
            raw = _fetch_raw_by_uid(m, str(imap_uid_db), m._account)  # type: ignore
            if raw:
                return raw, first, str(imap_uid_db)

    # 2) Message-ID search po složkách
    for fld in folders:
        if not _imap_select_safe(m, fld):
            continue
        uid = _search_message_id(m, message_id)
        if uid:
            raw = _fetch_raw_by_uid(m, uid, m._account)  # type: ignore
            if raw:
                return raw, fld, uid
    return None


def get_candidates(limit: int | None = None) -> list[dict]:
    """Vyber emaily k backfillu."""
    conn = get_conn()
    cur = conn.cursor()
    sql = """
        SELECT e.id, e.source_id, e.mailbox, e.folder, e.imap_uid, e.subject
        FROM email_messages e
        WHERE e.has_attachments = TRUE
          AND e.is_spam = FALSE
          AND NOT EXISTS (
              SELECT 1 FROM attachments a
              WHERE a.source_type='email' AND a.source_record_id = e.id
          )
        ORDER BY e.sent_at DESC
    """
    if limit:
        sql += f" LIMIT {int(limit)}"
    cur.execute(sql)
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [
        {"uuid": r[0], "msg_id": r[1], "mailbox": r[2],
         "folder": r[3], "imap_uid": r[4], "subject": r[5] or ""}
        for r in rows
    ]


def backfill_one(cand: dict) -> tuple[bool, str]:
    """Zpracuj jeden email. Vrací (ok, info_msg)."""
    acc = _account_for(cand["mailbox"])
    if not acc:
        return False, f"account not found for mailbox={cand['mailbox']}"
    if not acc.get("host"):
        return False, f"account host empty (env vars?) for {cand['mailbox']}"

    try:
        m = connect(acc)
    except Exception as e:
        return False, f"IMAP connect error: {e}"

    # Hack: nesem account dovnitř helperů přes _account atribut
    m._account = acc  # type: ignore

    folders = _candidate_folders(cand["folder"], acc["host"])
    try:
        found = find_message(m, cand["msg_id"], cand["imap_uid"], folders)
    except Exception as e:
        try:
            m.logout()
        except Exception:
            pass
        return False, f"find_message error: {e}"

    if not found:
        try:
            m.logout()
        except Exception:
            pass
        return False, f"not found in folders={folders}"

    raw_bytes, fld_used, uid_used = found
    try:
        m.logout()
    except Exception:
        pass

    # Parse + extract attachments (recyklujeme funkci z ingest_email.py)
    try:
        msg = email_mod.message_from_bytes(raw_bytes)
        attachments = _extract_attachments(msg)
    except Exception as e:
        return False, f"MIME parse/extract error: {e}"

    if not attachments:
        return False, f"MIME nemá žádné přílohy (možná přesně header has_attachments=TRUE byl chybný)"

    # Ulož na disk + do DB
    conn = get_conn()
    cur = conn.cursor()
    try:
        _save_email_attachments(str(cand["uuid"]), attachments, cur)
        conn.commit()
    except Exception as e:
        conn.rollback()
        cur.close()
        conn.close()
        return False, f"DB save error: {e}"
    cur.close()
    conn.close()

    sizes = sum(a["size_bytes"] for a in attachments)
    return True, f"OK {len(attachments)} att, {sizes//1024} kB, folder={fld_used}, uid={uid_used}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="Max počet emailů")
    ap.add_argument("--id", type=str, default=None, help="Backfill jen 1 konkrétní email_id (UUID)")
    args = ap.parse_args()

    if args.id:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            "SELECT id, source_id, mailbox, folder, imap_uid, subject "
            "FROM email_messages WHERE id=%s",
            (args.id,)
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        if not row:
            log.error(f"email_id {args.id} neexistuje v DB")
            sys.exit(1)
        candidates = [{
            "uuid": row[0], "msg_id": row[1], "mailbox": row[2],
            "folder": row[3], "imap_uid": row[4], "subject": row[5] or "",
        }]
    else:
        candidates = get_candidates(limit=args.limit)

    if not candidates:
        log.info("Žádní kandidáti.")
        return

    log.info(f"Backfill {len(candidates)} email(ů)…\n")
    ok = fail = 0
    for c in candidates:
        log.info(f"→ {c['mailbox']} | {c['subject'][:60]}")
        log.info(f"   id={c['uuid']} folder={c['folder']} uid_db={c['imap_uid']}")
        success, info = backfill_one(c)
        if success:
            ok += 1
            log.info(f"   ✅ {info}\n")
        else:
            fail += 1
            log.warning(f"   ❌ {info}\n")

    log.info(f"=== Hotovo: OK={ok}, FAIL={fail}, total={len(candidates)} ===")


if __name__ == "__main__":
    main()

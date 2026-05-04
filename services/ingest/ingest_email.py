"""
Email ingest — všechny IMAP účty, posledních 7 dní.
"""

import os
import json
import re
import imaplib
import email
import email.header
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from dotenv import load_dotenv
from db import get_conn


def _extract_body(msg) -> str:
    """Extrahuje čistý text z emailu (plain text preferred)."""
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            cd = part.get_content_disposition()
            if ct == "text/plain" and cd != "attachment":
                try:
                    charset = part.get_content_charset() or "utf-8"
                    body = part.get_payload(decode=True).decode(charset, errors="replace")
                    break
                except Exception:
                    pass
        if not body:
            for part in msg.walk():
                if part.get_content_type() == "text/html" and part.get_content_disposition() != "attachment":
                    try:
                        charset = part.get_content_charset() or "utf-8"
                        html = part.get_payload(decode=True).decode(charset, errors="replace")
                        body = re.sub(r'<[^>]+>', ' ', html)
                        body = re.sub(r'\s+', ' ', body).strip()
                        break
                    except Exception:
                        pass
    else:
        try:
            charset = msg.get_content_charset() or "utf-8"
            body = msg.get_payload(decode=True).decode(charset, errors="replace")
        except Exception:
            pass
    return body[:4000]


def _find_unsubscribe(msg, body_text: str) -> str | None:
    """Najde unsubscribe URL z headeru nebo těla emailu."""
    header = msg.get("List-Unsubscribe", "")
    if header:
        m = re.search(r'<(https?://[^>]+)>', header)
        if m:
            return m.group(1)
    patterns = [
        r'https?://\S+unsubscribe\S*',
        r'https?://\S+odhlasit\S*',
        r'https?://\S+opt.?out\S*',
    ]
    for p in patterns:
        m = re.search(p, body_text, re.IGNORECASE)
        if m:
            url = m.group(0).rstrip('.,)')
            return url
    return None

load_dotenv(os.path.join(os.path.dirname(__file__), "../../.env"))

DAYS_BACK = 7

# Přílohy — vždy se zapisují do _ATTACHMENTS_DIR (container path).
# Na DEV byl bind mount /Users/pavel/Desktop/OmniFocus → /app/attachments,
# proto se do DB ukládala Mac cesta (host_prefix). Na PROD (Linux VM, žádný bind mount na Mac)
# se do DB ukládá přímo container path.
# Řízeno env var ATTACHMENTS_HOST_PREFIX — pokud prázdné/nenastavené (PROD), použije se _ATTACHMENTS_DIR.
_ATTACHMENTS_DIR     = "/app/attachments"
_MAC_ATTACHMENTS_DIR = os.getenv("ATTACHMENTS_HOST_PREFIX", "")  # DEV: "/Users/pavel/Desktop/OmniFocus", PROD: ""
_MAX_ATTACHMENT_SIZE = 50 * 1024 * 1024  # 50 MB


def _safe_filename(name: str) -> str:
    """Odstraní nebezpečné znaky z názvu souboru."""
    name = re.sub(r'[^\w.\-]', '_', name)
    return name[:200] or "attachment"


def _extract_attachments(msg) -> list[dict]:
    """Extrahuje přílohy z emailu jako list {filename, mime_type, data, size_bytes}."""
    result = []
    seen = set()
    for part in msg.walk():
        if part.get_content_disposition() != "attachment":
            continue
        try:
            raw_name = part.get_filename() or ""
            filename = decode_header_value(raw_name) if raw_name else f"attachment_{len(result)+1}"
            safe = _safe_filename(filename)
            # Deduplikace (stejný soubor vícekrát)
            if safe in seen:
                base, ext = os.path.splitext(safe)
                safe = f"{base}_{len(result)+1}{ext}"
            seen.add(safe)
            payload = part.get_payload(decode=True)
            if not payload:
                continue
            if len(payload) > _MAX_ATTACHMENT_SIZE:
                print(f"    SKIP příloha přes 50 MB: {filename}")
                continue
            result.append({
                "filename": filename,
                "safe_filename": safe,
                "mime_type": part.get_content_type() or "application/octet-stream",
                "data": payload,
                "size_bytes": len(payload),
            })
        except Exception as e:
            print(f"    WARN attachment extract: {e}")
    return result


def _save_email_attachments(email_uuid: str, attachments: list, cur) -> None:
    """Uloží přílohy na disk a zapíše záznamy do DB."""
    if not attachments:
        return
    email_dir = os.path.join(_ATTACHMENTS_DIR, str(email_uuid))
    try:
        os.makedirs(email_dir, exist_ok=True)
    except Exception as e:
        print(f"    WARN makedirs {email_dir}: {e}")
        return
    for att in attachments:
        file_path = os.path.join(email_dir, att["safe_filename"])
        try:
            with open(file_path, "wb") as f:
                f.write(att["data"])
            # storage_path: na DEV obsahuje Mac cestu (host overlay přes bind mount),
            # na PROD container cestu (žádný host overlay).
            storage_path = file_path.replace(_ATTACHMENTS_DIR, _MAC_ATTACHMENTS_DIR) if _MAC_ATTACHMENTS_DIR else file_path
            cur.execute("""
                INSERT INTO attachments
                    (source_type, source_record_id, filename, storage_path, mime_type, size_bytes)
                VALUES ('email', %s, %s, %s, %s, %s)
            """, (email_uuid, att["filename"], storage_path, att["mime_type"], att["size_bytes"]))
            print(f"      📎 příloha: {att['filename']} ({att['size_bytes']//1024} kB)")
        except Exception as e:
            print(f"    WARN attachment save {att['filename']}: {e}")

ACCOUNTS = [
    {"name": "brogi@dxpsolutions.cz",     "host": os.getenv("IMAP_HOST_DXPSOLUTIONS"), "port": 993, "ssl": True,  "user": os.getenv("IMAP_USER_DXPSOLUTIONS"),  "password": os.getenv("IMAP_PASSWORD_DXPSOLUTIONS")},
    {"name": "pavel@dxpsolutions.cz",     "host": os.getenv("IMAP_HOST_PAVEL"),        "port": 993, "ssl": True,  "user": os.getenv("IMAP_USER_PAVEL"),         "password": os.getenv("IMAP_PASSWORD_PAVEL")},
    {"name": "support@dxpsolutions.cz",   "host": os.getenv("IMAP_HOST_SUPPORT"),      "port": 993, "ssl": True,  "user": os.getenv("IMAP_USER_SUPPORT"),       "password": os.getenv("IMAP_PASSWORD_SUPPORT")},
    {"name": "servicedesk@dxpsolutions.cz","host": os.getenv("IMAP_HOST_SERVICEDESK"), "port": 993, "ssl": True,  "user": os.getenv("IMAP_USER_SERVICEDESK"),   "password": os.getenv("IMAP_PASSWORD_SERVICEDESK")},
    {"name": "dxpavel@gmail.com",         "host": os.getenv("IMAP_HOST_GMAIL"),        "port": 993, "ssl": True,  "user": os.getenv("IMAP_USER_GMAIL"),         "password": os.getenv("IMAP_PASSWORD_GMAIL")},
    {"name": "dxpavel@icloud.com",        "host": os.getenv("IMAP_HOST_ICLOUD"),       "port": 993, "ssl": True,  "user": os.getenv("IMAP_USER_ICLOUD"),        "password": os.getenv("IMAP_PASSWORD_ICLOUD"), "fetch_cmd": "BODY[]"},
    {"name": "padre@seznam.cz",           "host": os.getenv("IMAP_HOST_SEZNAM"),       "port": 993, "ssl": True,  "user": os.getenv("IMAP_USER_SEZNAM"),        "password": os.getenv("IMAP_PASSWORD_SEZNAM"),        "supports_idle": False},
    {"name": "postapro@dxpavel.cz",       "host": os.getenv("IMAP_HOST_FORPSI"),       "port": 143, "ssl": False, "user": os.getenv("IMAP_USER_FORPSI"),        "password": os.getenv("IMAP_PASSWORD_FORPSI")},
    {"name": "zamecnictvi.rozdalovice@gmail.com",     "host": os.getenv("IMAP_HOST_ZAMECNICTVI"), "port": 993, "ssl": True,  "user": os.getenv("IMAP_USER_ZAMECNICTVI"),   "password": os.getenv("IMAP_PASSWORD_ZAMECNICTVI")},
]


def decode_header_value(val):
    if not val:
        return ""
    parts = email.header.decode_header(val)
    result = []
    for part, enc in parts:
        if isinstance(part, bytes):
            result.append(part.decode(enc or "utf-8", errors="replace"))
        else:
            result.append(part)
    return " ".join(result)


def connect(account: dict) -> imaplib.IMAP4:
    if account["ssl"]:
        m = imaplib.IMAP4_SSL(account["host"], account["port"])
    else:
        m = imaplib.IMAP4(account["host"], account["port"])
        m.starttls()
    m.login(account["user"], account["password"])
    return m


def fetch_messages(account: dict, since: datetime) -> list[dict]:
    since_str = since.strftime("%d-%b-%Y")
    m = connect(account)
    m.select("INBOX", readonly=True)
    _, data = m.uid('SEARCH', None, f'SINCE {since_str}')  # UID-based search → skutečná UID
    # 2026-05-04: iCloud občas vrátí data=[None] při dočasných glitchích nebo
    # prázdném výsledku. `None.split()` → AttributeError. Ošetříme.
    uids = (data[0] or b"").split() if data else []
    messages = []
    fetch_cmd = "(BODY[])" if account.get("fetch_cmd") == "BODY[]" else "(RFC822)"
    for uid in uids:
        try:
            _, raw = m.uid('FETCH', uid, fetch_cmd)  # UID-based fetch
            raw_bytes = next((item[1] for item in raw if isinstance(item, tuple)), None)
            if not raw_bytes:
                continue
            msg = email.message_from_bytes(raw_bytes)

            message_id = msg.get("Message-ID", f"uid-{uid.decode()}-{account['name']}").strip()
            subject = decode_header_value(msg.get("Subject", ""))
            from_addr = decode_header_value(msg.get("From", ""))
            to_raw = decode_header_value(msg.get("To", "")) or ""
            to_addrs = [a.strip() for a in to_raw.split(",") if a.strip()]

            sent_at = None
            date_str = msg.get("Date")
            if date_str:
                try:
                    sent_at = parsedate_to_datetime(date_str)
                    if sent_at.tzinfo is None:
                        sent_at = sent_at.replace(tzinfo=timezone.utc)
                except Exception:
                    pass

            attachments = _extract_attachments(msg)
            has_attachments = bool(attachments)

            body_text = _extract_body(msg)
            unsubscribe_url = _find_unsubscribe(msg, body_text)

            # RFC 5322 / 2369 hlavičky pro decision_rules + threading + spam detection
            # str() konverze ošetří email.header.Header objekt (multi-line, encoded)
            def _hdr(name: str):
                v = msg.get(name)
                return str(v) if v is not None else None

            headers = {
                # threading (RFC 5322 §3.6.4)
                "Message-ID":       _hdr("Message-ID"),
                "In-Reply-To":      _hdr("In-Reply-To"),
                "References":       _hdr("References"),
                # mailing list (RFC 2369)
                "List-Id":          _hdr("List-Id"),
                "List-Unsubscribe": _hdr("List-Unsubscribe"),
                "List-Post":        _hdr("List-Post"),
                # auto-replies / bounces (RFC 3834 / RFC 3464)
                "Auto-Submitted":   _hdr("Auto-Submitted"),
                # encrypted detection (S/MIME, PGP)
                "Content-Type":     _hdr("Content-Type"),
                # akčnost (TO vs CC vs BCC)
                "Cc":               _hdr("Cc"),
                "Bcc":              _hdr("Bcc"),
                # spam detection / bounce
                "Reply-To":         _hdr("Reply-To"),
                "Return-Path":      _hdr("Return-Path"),
                "X-Mailer":         _hdr("X-Mailer"),
                # M1: bot vlastní reply marker (decision_rules `self_sent` rule
                # priority 5 → skip klasifikace pokud header existuje)
                "X-Brogi-Auto":     _hdr("X-Brogi-Auto"),
            }

            # Pro threading (blocker D1): extrahovat z headers do top-level
            in_reply_to = headers.get("In-Reply-To") or None
            if in_reply_to:
                in_reply_to = in_reply_to.strip().strip("<>").strip()

            messages.append({
                "source_id": message_id,
                "mailbox": account["name"],
                "from_address": from_addr,
                "to_addresses": to_addrs,
                "subject": subject,
                "sent_at": sent_at,
                "has_attachments": has_attachments,
                "imap_uid": int(uid.decode() if isinstance(uid, bytes) else uid),
                "body_text": body_text,
                "unsubscribe_url": unsubscribe_url,
                "attachments": attachments,
                "rfc_message_id": message_id.strip().strip("<>").strip() if message_id else None,
                "in_reply_to": in_reply_to,
                "raw_payload": {
                    "message_id": message_id,
                    "subject": subject,
                    "from": from_addr,
                    "to": to_addrs,
                    "date": date_str,
                    "has_attachments": has_attachments,
                    "headers": headers,
                },
            })
        except Exception as e:
            print(f"    WARN uid {uid}: {e}")
    m.logout()
    return messages


def upsert_messages(messages: list) -> tuple[int, int]:
    conn = get_conn()
    cur = conn.cursor()
    new_count = 0
    skip_count = 0
    for msg in messages:
        cur.execute("""
            INSERT INTO email_messages
                (source_type, source_id, raw_payload, mailbox, from_address,
                 to_addresses, subject, sent_at, has_attachments, imap_uid,
                 body_text, unsubscribe_url, message_id, in_reply_to)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (source_id) DO UPDATE SET
                body_text = COALESCE(EXCLUDED.body_text, email_messages.body_text),
                unsubscribe_url = COALESCE(EXCLUDED.unsubscribe_url, email_messages.unsubscribe_url),
                message_id = COALESCE(EXCLUDED.message_id, email_messages.message_id),
                in_reply_to = COALESCE(EXCLUDED.in_reply_to, email_messages.in_reply_to)
            RETURNING id, (xmax = 0) AS is_new, is_spam
        """, (
            "email",
            msg["source_id"],
            json.dumps(msg["raw_payload"]),
            msg["mailbox"],
            msg["from_address"],
            msg["to_addresses"],
            msg["subject"],
            msg["sent_at"],
            msg["has_attachments"],
            msg["imap_uid"],
            msg.get("body_text"),
            msg.get("unsubscribe_url"),
            msg.get("rfc_message_id"),
            msg.get("in_reply_to"),
        ))
        row = cur.fetchone()
        email_uuid, is_new, is_spam_db = row[0], row[1], row[2]

        # Threading: pokud je nový, dohledat thread_id z parent (in_reply_to → message_id)
        # Pokud parent nenajdeme, thread_id = vlastní id (root threadu).
        if is_new:
            parent_id = None
            if msg.get("in_reply_to"):
                cur.execute(
                    "SELECT id, thread_id FROM email_messages WHERE message_id = %s LIMIT 1",
                    (msg["in_reply_to"],)
                )
                parent_row = cur.fetchone()
                if parent_row:
                    parent_id = parent_row[1] or parent_row[0]  # parent.thread_id nebo parent.id
            cur.execute(
                "UPDATE email_messages SET thread_id = %s WHERE id = %s",
                (parent_id or email_uuid, email_uuid)
            )
        if is_new:
            new_count += 1
        else:
            skip_count += 1

        # Přílohy: ulož pokud (a) email má přílohy v MIME, (b) NENÍ spam,
        # (c) ještě nejsou v DB. Pokrývá nový i duplicitní case (BUG-002 fix).
        if msg.get("attachments") and not is_spam_db:
            cur.execute(
                "SELECT COUNT(*) FROM attachments WHERE source_type='email' AND source_record_id=%s",
                (str(email_uuid),)
            )
            if cur.fetchone()[0] == 0:
                _save_email_attachments(str(email_uuid), msg["attachments"], cur)
    conn.commit()
    conn.close()
    return new_count, skip_count


if __name__ == "__main__":
    since = datetime.now(tz=timezone.utc) - timedelta(days=DAYS_BACK)
    print(f"Email ingest — od {since.strftime('%Y-%m-%d')}\n")

    total_new = 0
    for acc in ACCOUNTS:
        print(f"  {acc['name']} ...", end=" ", flush=True)
        try:
            msgs = fetch_messages(acc, since)
            new_c, skip_c = upsert_messages(msgs)
            print(f"{len(msgs)} zpráv → nových: {new_c}, duplikáty: {skip_c}")
            total_new += new_c
        except Exception as e:
            print(f"CHYBA: {e}")

    print(f"\nCelkem nových zpráv: {total_new}")

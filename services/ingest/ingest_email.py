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
    uids = data[0].split()
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
            to_raw = decode_header_value(msg.get("To", ""))
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

            has_attachments = any(
                part.get_content_disposition() == "attachment"
                for part in msg.walk()
            )

            body_text = _extract_body(msg)
            unsubscribe_url = _find_unsubscribe(msg, body_text)

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
                "raw_payload": {
                    "message_id": message_id,
                    "subject": subject,
                    "from": from_addr,
                    "to": to_addrs,
                    "date": date_str,
                    "has_attachments": has_attachments,
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
                 body_text, unsubscribe_url)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (source_id) DO UPDATE SET
                body_text = COALESCE(EXCLUDED.body_text, email_messages.body_text),
                unsubscribe_url = COALESCE(EXCLUDED.unsubscribe_url, email_messages.unsubscribe_url)
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
        ))
        if cur.rowcount:
            new_count += 1
        else:
            skip_count += 1
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

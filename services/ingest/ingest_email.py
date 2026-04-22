"""
Email ingest — všechny IMAP účty, posledních 7 dní.
"""

import os
import json
import imaplib
import email
import email.header
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from dotenv import load_dotenv
from db import get_conn

load_dotenv(os.path.join(os.path.dirname(__file__), "../../.env"))

DAYS_BACK = 7

ACCOUNTS = [
    {"name": "brogi@dxpsolutions.cz",     "host": os.getenv("IMAP_HOST_DXPSOLUTIONS"), "port": 993, "ssl": True,  "user": os.getenv("IMAP_USER_DXPSOLUTIONS"),  "password": os.getenv("IMAP_PASSWORD_DXPSOLUTIONS")},
    {"name": "pavel@dxpsolutions.cz",     "host": os.getenv("IMAP_HOST_PAVEL"),        "port": 993, "ssl": True,  "user": os.getenv("IMAP_USER_PAVEL"),         "password": os.getenv("IMAP_PASSWORD_PAVEL")},
    {"name": "support@dxpsolutions.cz",   "host": os.getenv("IMAP_HOST_SUPPORT"),      "port": 993, "ssl": True,  "user": os.getenv("IMAP_USER_SUPPORT"),       "password": os.getenv("IMAP_PASSWORD_SUPPORT")},
    {"name": "servicedesk@dxpsolutions.cz","host": os.getenv("IMAP_HOST_SERVICEDESK"), "port": 993, "ssl": True,  "user": os.getenv("IMAP_USER_SERVICEDESK"),   "password": os.getenv("IMAP_PASSWORD_SERVICEDESK")},
    {"name": "dxpavel@gmail.com",         "host": os.getenv("IMAP_HOST_GMAIL"),        "port": 993, "ssl": True,  "user": os.getenv("IMAP_USER_GMAIL"),         "password": os.getenv("IMAP_PASSWORD_GMAIL")},
    {"name": "dxpavel@icloud.com",        "host": os.getenv("IMAP_HOST_ICLOUD"),       "port": 993, "ssl": True,  "user": os.getenv("IMAP_USER_ICLOUD"),        "password": os.getenv("IMAP_PASSWORD_ICLOUD"), "fetch_cmd": "BODY[]"},
    {"name": "padre@seznam.cz",           "host": os.getenv("IMAP_HOST_SEZNAM"),       "port": 993, "ssl": True,  "user": os.getenv("IMAP_USER_SEZNAM"),        "password": os.getenv("IMAP_PASSWORD_SEZNAM")},
    {"name": "postapro@dxpavel.cz",       "host": os.getenv("IMAP_HOST_FORPSI"),       "port": 143, "ssl": False, "user": os.getenv("IMAP_USER_FORPSI"),        "password": os.getenv("IMAP_PASSWORD_FORPSI")},
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
    _, data = m.search(None, f'SINCE {since_str}')
    uids = data[0].split()
    messages = []
    fetch_cmd = "(BODY[])" if account.get("fetch_cmd") == "BODY[]" else "(RFC822)"
    for uid in uids:
        try:
            _, raw = m.fetch(uid, fetch_cmd)
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

            messages.append({
                "source_id": message_id,
                "mailbox": account["name"],
                "from_address": from_addr,
                "to_addresses": to_addrs,
                "subject": subject,
                "sent_at": sent_at,
                "has_attachments": has_attachments,
                "imap_uid": int(uid.decode() if isinstance(uid, bytes) else uid),
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
                 to_addresses, subject, sent_at, has_attachments, imap_uid)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (source_id) DO NOTHING
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

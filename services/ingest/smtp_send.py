"""
BrogiASIST — SMTP odesílání bot replies (M1 / BUG-010 fix).

Per docs/feature-specs/FEATURE-AI-CASCADE-v1.md a BUGS.md BUG-010:
varianta (d) Direct SMTP. Pavel rozhodnutí 2026-05-04.

Funkce:
  send_reply(account_name, to, subject, body, in_reply_to=None,
             references=None, x_brogi_auto="reply", html=False)
    - Pošle email přes SMTP s X-Brogi-Auto headerem
    - APPEND kopii do Sent folderu daného účtu (aby Pavel reply
      viděl v Mail.app / Gmail web)
    - Vrací (ok: bool, message_id: str|None, error: str|None)

  is_brogi_auto(headers: dict) -> bool
    - True pokud raw_payload.headers obsahuje X-Brogi-Auto
    - Použijí ingest filter + classify (decision_engine self_sent rule)

SMTP creds:
  Stejné jako IMAP — `user` / `password` z ACCOUNTS. Server hostname
  z SMTP_MAP per IMAP host (smtp.X analogicky imap.X).

Sent folder pro APPEND:
  - Gmail:    "[Gmail]/Sent Mail"
  - iCloud:   "Sent Messages"
  - Forpsi:   "INBOX.Sent"
  - Synology: "INBOX.Sent" (Cyrus)
  - Seznam:   "Sent"
"""
from __future__ import annotations

import logging
import smtplib
import imaplib
from email.message import EmailMessage
from email.utils import make_msgid, formatdate

from ingest_email import ACCOUNTS, connect as imap_connect

log = logging.getLogger(__name__)

# Mapování IMAP host → (SMTP host, port, security)
SMTP_MAP = {
    "imap.gmail.com":       ("smtp.gmail.com",     587, "starttls"),
    "imap.mail.me.com":     ("smtp.mail.me.com",   587, "starttls"),
    "imap.forpsi.com":      ("smtp.forpsi.com",    587, "starttls"),
    "mail.dxpsolutions.cz": ("mail.dxpsolutions.cz", 587, "starttls"),
    "imap.seznam.cz":       ("smtp.seznam.cz",     465, "ssl"),
}

# IMAP Sent folder per host
SENT_MAP = {
    "imap.gmail.com":       "[Gmail]/Sent Mail",
    "imap.mail.me.com":     "Sent Messages",
    "imap.forpsi.com":      "INBOX.Sent",
    "mail.dxpsolutions.cz": "INBOX.Sent",
    "imap.seznam.cz":       "Sent",
}


def _account(name: str) -> dict | None:
    for acc in ACCOUNTS:
        if acc["name"] == name:
            return acc
    return None


def _smtp_open(host: str, port: int, security: str, user: str, password: str, timeout: int = 20):
    if security == "ssl":
        s = smtplib.SMTP_SSL(host, port, timeout=timeout)
    else:
        s = smtplib.SMTP(host, port, timeout=timeout)
        s.starttls()
    s.login(user, password)
    return s


def _imap_append_sent(account_name: str, msg: EmailMessage) -> bool:
    """APPEND kopii do Sent folderu přes IMAP. Aby Pavel reply viděl v Mail.app."""
    acc = _account(account_name)
    if not acc:
        return False
    sent_folder = SENT_MAP.get(acc.get("host", ""))
    if not sent_folder:
        log.warning(f"smtp_send: žádný SENT_MAP pro host {acc.get('host')!r}, skip APPEND")
        return False
    try:
        m = imap_connect(acc)
        flags = r"(\Seen)"
        date_time = imaplib.Time2Internaldate(__import__("time").time())
        typ, _ = m.append(sent_folder, flags, date_time, msg.as_bytes())
        m.logout()
        if typ != "OK":
            log.warning(f"smtp_send: APPEND {sent_folder!r} returned {typ}")
            return False
        return True
    except Exception as e:
        log.error(f"smtp_send: APPEND failed ({account_name} → {sent_folder}): {e}")
        return False


def send_reply(
    account_name: str,
    to: str,
    subject: str,
    body: str,
    *,
    in_reply_to: str | None = None,
    references: str | None = None,
    x_brogi_auto: str = "reply",
    html: bool = False,
) -> tuple[bool, str | None, str | None]:
    """Pošle bot reply přes SMTP + APPEND do Sent.

    Vrací (ok, message_id, error).
    """
    acc = _account(account_name)
    if not acc:
        return False, None, f"unknown account {account_name!r}"
    smtp = SMTP_MAP.get(acc.get("host", ""))
    if not smtp:
        return False, None, f"no SMTP_MAP for host {acc.get('host')!r}"
    smtp_host, smtp_port, smtp_sec = smtp

    user = acc.get("user")
    password = acc.get("password")
    if not user or not password:
        return False, None, f"missing creds for {account_name}"

    msg = EmailMessage()
    from_addr = account_name  # email jako From
    msg["From"] = from_addr
    msg["To"] = to
    msg["Subject"] = subject
    mid = make_msgid(domain="brogiasist")
    msg["Message-ID"] = mid
    msg["Date"] = formatdate(localtime=True)
    if in_reply_to:
        msg["In-Reply-To"] = in_reply_to if in_reply_to.startswith("<") else f"<{in_reply_to}>"
    if references:
        msg["References"] = references
    msg["X-Brogi-Auto"] = x_brogi_auto
    msg["Auto-Submitted"] = "auto-replied"

    if html:
        msg.set_content("(viz HTML část)")
        msg.add_alternative(body, subtype="html")
    else:
        msg.set_content(body)

    try:
        s = _smtp_open(smtp_host, smtp_port, smtp_sec, user, password)
        s.send_message(msg)
        s.quit()
        log.info(f"smtp_send OK: {account_name} → {to} (msgid={mid})")
    except Exception as e:
        log.error(f"smtp_send FAILED: {account_name} → {to}: {e}")
        return False, mid, str(e)

    # APPEND do Sent (best-effort, neztrácí success pokud selže)
    appended = _imap_append_sent(account_name, msg)
    if not appended:
        log.warning(f"smtp_send: APPEND do Sent selhal — email odeslán ale není v Sent ({account_name})")

    return True, mid, None


def is_brogi_auto(headers: dict) -> bool:
    """True pokud email má X-Brogi-Auto header (= bot vlastní reply, skip ingest)."""
    if not headers:
        return False
    return bool(headers.get("X-Brogi-Auto"))

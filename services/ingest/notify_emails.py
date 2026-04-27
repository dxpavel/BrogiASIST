"""
BrogiASIST — Telegram notifikace pro klasifikované emaily
Spouští se každých 2 min ze scheduleru.
"""
import logging
from html import escape
from db import get_conn
from telegram_notify import send
from chroma_client import find_repeat_action

log = logging.getLogger(__name__)

TYP_ICON = {
    # Email Semantics v1 (per docs/brogiasist-semantics-v1.md sekce 1)
    "ÚKOL":       "📋",
    "DOKLAD":     "📄",
    "NABÍDKA":    "💼",
    "NOTIFIKACE": "🔔",
    "POZVÁNKA":   "📅",
    "INFO":       "ℹ️",
    "ERROR":      "⚠️",
    "LIST":       "📰",
    "ENCRYPTED":  "🔒",
    # Legacy (fallback dokud staré emaily klasifikované neproletí)
    "FAKTURA":    "📄",
    "NEWSLETTER": "📰",
    "POTVRZENÍ":  "✔️",
}

# Per-TYP TG tlačítka (per spec sekce 7)
SKIP_TYPY = {"SPAM", "ESHOP", "LIST"}  # LIST: auto-2hotovo, žádná TG zpráva


def _btn(label: str, action: str, eid: str) -> dict:
    return {"text": label, "callback_data": f"email:{action}:{eid}"}


def _buttons_for_typ(typ: str, email_id: str, has_unsubscribe: bool = False) -> list:
    """Univerzální 3×3 layout pro všechny TYPy (Pavlovo rozhodnutí 2026-04-27).

    Callback_data zůstává `email:<action>:<id>` (backward compat).
    `2unsub` se ukáže jen když email má `List-Unsubscribe` header.
    `ENCRYPTED` má navíc extra řádek `👁 Otevřu sám` (action=precteno).
    """
    eid = email_id

    row2 = [_btn("📅 2cal", "cal", eid),
            _btn("📝 2note", "note", eid)]
    if has_unsubscribe:
        row2.append(_btn("🚫 2unsub", "unsub", eid))

    universal = [
        [_btn("✅ 2hotovo", "hotovo", eid),
         _btn("📥 2of",     "of",     eid),
         _btn("⏰ 2rem",    "rem",    eid)],
        row2,
        [_btn("⏭ 2skip",   "skip",   eid),
         _btn("🗑 2del",    "del",    eid),
         _btn("🚫 2spam",   "spam",   eid)],
    ]

    if typ == "ENCRYPTED":
        return [[_btn("👁 Otevřu sám", "precteno", eid)]] + universal

    return universal


def _render_buttons(typ: str, email_id: str, has_unsubscribe: bool = False) -> list:
    """Backward-compat alias pro starší volání."""
    return _buttons_for_typ(typ, email_id, has_unsubscribe)


def notify_classified_emails():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, mailbox, from_address, subject, typ, firma, ai_confidence, body_text,
               raw_payload->'headers'->>'List-Unsubscribe' AS list_unsub
        FROM email_messages
        WHERE typ IS NOT NULL
          AND is_spam = FALSE
          AND tg_notified_at IS NULL
          AND typ NOT IN ('SPAM', 'ESHOP')
          AND human_reviewed = FALSE
        ORDER BY sent_at DESC
        LIMIT 20
    """)
    rows = cur.fetchall()

    for email_id, mailbox, from_addr, subject, typ, firma, confidence, body, list_unsub in rows:
        icon = TYP_ICON.get(typ, "📧")
        conf_str = f"{int((confidence or 0)*100)}%" if confidence else "?"
        short_from = from_addr.split("<")[-1].rstrip(">") if "<" in (from_addr or "") else (from_addr or "?")
        mb = mailbox.split("@")[0] if mailbox else "?"

        # Zkontroluj ChromaDB — opakující se vzor?
        repeat_action = find_repeat_action(from_addr or "", subject or "", body or "")
        if repeat_action:
            # Auto-apply bez TG dotazu
            from telegram_callback import _email_action
            _email_action(str(email_id), repeat_action)
            action_label = {
                "of": "OF", "rem": "Reminder", "note": "Note",
                "hotovo": "Hotovo", "spam": "Spam", "del": "Smazáno",
                "precteno": "Přečteno",
            }.get(repeat_action, repeat_action)
            send(
                f"🔁 <b>Opakuji akci: {action_label}</b>\n"
                f"Od: <code>{short_from}</code>\n"
                f"Předmět: {subject or '(bez předmětu)'}"
            )
            cur.execute("UPDATE email_messages SET tg_notified_at=NOW() WHERE id=%s", (email_id,))
            log.info(f"chroma auto-apply: {repeat_action} email_id={email_id}")
            continue

        text = (
            f"{icon} <b>{escape(typ)}</b>  <code>{escape(mb)}</code>  <i>{conf_str}</i>\n"
            f"Od: <code>{escape(short_from)}</code>\n"
            f"Předmět: {escape(subject or '(bez předmětu)')}"
        )
        if firma:
            text += f"\nFirma: <b>{escape(firma)}</b>"

        buttons = _render_buttons(typ, str(email_id), has_unsubscribe=bool(list_unsub))
        result = send(text, buttons)

        if result:
            msg_id = result.get("message_id")
            cur.execute("UPDATE email_messages SET tg_notified_at=NOW(), tg_message_id=%s WHERE id=%s", (msg_id, email_id))
            log.info(f"TG notify sent: {typ} id={email_id}")
        else:
            log.warning(f"TG notify FAILED: id={email_id}")

    conn.commit()
    cur.close()
    conn.close()
    if rows:
        log.info(f"notify_classified_emails: odesláno {len(rows)} notifikací")

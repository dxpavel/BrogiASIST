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
    "ÚKOL":       "📋",
    "FAKTURA":    "📄",
    "NOTIFIKACE": "🔔",
    "NABÍDKA":    "💼",
    "INFO":       "ℹ️",
    "NEWSLETTER": "📰",
    "POTVRZENÍ":  "✔️",
}

BUTTONS = {
    "ÚKOL": [
        [
            {"text": "📋 OF",        "callback_data": "email:of:{id}"},
            {"text": "⏰ REM",        "callback_data": "email:rem:{id}"},
            {"text": "📝 NOTE",       "callback_data": "email:note:{id}"},
        ],[
            {"text": "✅ Hotovo",    "callback_data": "email:hotovo:{id}"},
            {"text": "⏳ Čeká",      "callback_data": "email:ceka:{id}"},
            {"text": "🗑️ Spam",     "callback_data": "email:spam:{id}"},
            {"text": "⏭️ Skip",     "callback_data": "email:skip:{id}"},
        ],
    ],
    "FAKTURA": [[
        {"text": "✅ Zaplaceno", "callback_data": "email:hotovo:{id}"},
        {"text": "📋 OF",        "callback_data": "email:of:{id}"},
        {"text": "📝 NOTE",      "callback_data": "email:note:{id}"},
        {"text": "⏭️ Skip",     "callback_data": "email:skip:{id}"},
    ]],
    "NOTIFIKACE": [[
        {"text": "📋 OF",        "callback_data": "email:of:{id}"},
        {"text": "👁️ Přečteno", "callback_data": "email:precteno:{id}"},
        {"text": "🗑️ Spam",     "callback_data": "email:spam:{id}"},
        {"text": "⏭️ Skip",     "callback_data": "email:skip:{id}"},
    ]],
    "NABÍDKA": [[
        {"text": "📋 OF",        "callback_data": "email:of:{id}"},
        {"text": "📝 NOTE",      "callback_data": "email:note:{id}"},
        {"text": "🗑️ Spam",     "callback_data": "email:spam:{id}"},
        {"text": "⏭️ Skip",     "callback_data": "email:skip:{id}"},
    ]],
    "INFO": [[
        {"text": "📝 NOTE",      "callback_data": "email:note:{id}"},
        {"text": "👁️ Přečteno", "callback_data": "email:precteno:{id}"},
        {"text": "⏭️ Skip",     "callback_data": "email:skip:{id}"},
    ]],
    "NEWSLETTER": [[
        {"text": "👁️ Přečteno", "callback_data": "email:precteno:{id}"},
        {"text": "🚫 Odhlásit", "callback_data": "email:unsub:{id}"},
        {"text": "🗑️ Spam",     "callback_data": "email:spam:{id}"},
        {"text": "⏭️ Skip",     "callback_data": "email:skip:{id}"},
    ]],
    "POTVRZENÍ": [[
        {"text": "📝 NOTE",      "callback_data": "email:note:{id}"},
        {"text": "👁️ Přečteno", "callback_data": "email:precteno:{id}"},
        {"text": "⏭️ Skip",     "callback_data": "email:skip:{id}"},
    ]],
}

SKIP_TYPY = {"SPAM", "ESHOP"}


def _render_buttons(typ: str, email_id: str) -> list | None:
    template = BUTTONS.get(typ)
    if not template:
        return None
    return [[{**b, "callback_data": b["callback_data"].replace("{id}", email_id)} for b in row]
            for row in template]


def notify_classified_emails():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, mailbox, from_address, subject, typ, firma, ai_confidence, body_text
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

    for email_id, mailbox, from_addr, subject, typ, firma, confidence, body in rows:
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
                "hotovo": "Hotovo", "spam": "Spam", "precteno": "Přečteno",
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

        buttons = _render_buttons(typ, str(email_id))
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

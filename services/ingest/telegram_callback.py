"""
BrogiASIST — Telegram callback handler (polling smyčka).

Po BUG-001 refactoru (2026-05-04): tento soubor obsahuje JEN TG-specific
infrastrukturu (callback offset persist, polling loop, dispatch).
Sdílená email_action / email_undo logika je v `email_actions.py`.
"""
import logging
import time

from db import get_conn
from telegram_notify import get_updates, answer_callback, send
from email_actions import (
    email_action,
    ACTION_LABEL,
    UNDO_REVERSIBLE,
    _mark_spam,
    _get_email_from,
)

log = logging.getLogger(__name__)

OFFSET_KEY = "tg_callback_offset"


def _load_offset() -> int:
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT value FROM config WHERE key=%s", (OFFSET_KEY,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        return int(row[0]) if row else 0
    except Exception as e:
        log.error(f"_load_offset: {e}")
        return 0


def _save_offset(value: int) -> None:
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO config (key, value, module) VALUES (%s, %s, 'telegram')
            ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, updated_at=NOW()
        """, (OFFSET_KEY, str(value)))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        log.error(f"_save_offset: {e}")


def _process_text_message(msg: dict):
    """M1 final: pokud chat má pending reply v tg_pending_replies, vezme
    text z msg a pošle ho jako reply přes smtp_send. Pak vyčistí state.

    Speciální: text == '/cancel' → jen zruší pending bez odeslání.
    """
    chat_id = (msg.get("chat") or {}).get("id")
    text = (msg.get("text") or "").strip()
    if not chat_id or not text:
        return

    # Načíst pending state
    try:
        conn = get_conn(); cur = conn.cursor()
        cur.execute("""
            SELECT email_id, started_at, ttl_minutes
            FROM tg_pending_replies
            WHERE chat_id=%s
        """, (chat_id,))
        row = cur.fetchone()
        cur.close(); conn.close()
    except Exception as e:
        log.error(f"_process_text_message: pending load failed: {e}")
        return

    if not row:
        return  # žádný pending — ignoruj text (Pavel napsal něco jen tak)

    email_id, started_at, ttl = row

    # TTL check
    from datetime import datetime, timezone
    age_min = (datetime.now(timezone.utc) - started_at).total_seconds() / 60
    if age_min > ttl:
        log.warning(f"reply pending expired: chat={chat_id} email={email_id} age={age_min:.0f}min")
        try:
            conn = get_conn(); cur = conn.cursor()
            cur.execute("DELETE FROM tg_pending_replies WHERE chat_id=%s", (chat_id,))
            conn.commit(); cur.close(); conn.close()
        except Exception:
            pass
        send("⚠️ <b>Reply timeout</b> — pending bylo starší než TTL, smazáno.")
        return

    # /cancel?
    if text.lower() in ("/cancel", "cancel", "zrusit", "zruš"):
        try:
            conn = get_conn(); cur = conn.cursor()
            cur.execute("DELETE FROM tg_pending_replies WHERE chat_id=%s", (chat_id,))
            conn.commit(); cur.close(); conn.close()
        except Exception:
            pass
        send(f"🚫 <b>Reply zrušen</b> pro email <code>{email_id}</code>")
        return

    # Pošli reply
    try:
        conn = get_conn(); cur = conn.cursor()
        cur.execute("SELECT mailbox, from_address, subject, message_id FROM email_messages WHERE id=%s", (email_id,))
        em_row = cur.fetchone()
        cur.close(); conn.close()
    except Exception as e:
        log.error(f"reply: load email failed: {e}")
        send(f"⚠️ DB chyba: <code>{e}</code>")
        return

    if not em_row:
        send("⚠️ Email nenalezen — pending zrušen.")
        try:
            conn = get_conn(); cur = conn.cursor()
            cur.execute("DELETE FROM tg_pending_replies WHERE chat_id=%s", (chat_id,))
            conn.commit(); cur.close(); conn.close()
        except Exception:
            pass
        return

    mailbox, from_addr, subject, msg_id = em_row
    import re
    m = re.search(r'<([^>]+@[^>]+)>', from_addr or "")
    to_addr = m.group(1).strip() if m else (from_addr or "").strip()
    if not to_addr or "@" not in to_addr:
        send(f"⚠️ Nelze extrahovat email z <code>{from_addr or ''}</code>")
        return

    reply_subject = subject if (subject or "").lower().startswith("re:") else f"Re: {subject or '(no subject)'}"
    body = text + "\n\n--\nOdesláno z BrogiASIST"

    from email_actions import _bridge_call  # noqa: F401  ← jen pro side-effect (httpx)
    from smtp_send import send_reply
    ok, sent_mid, err = send_reply(
        account_name=mailbox,
        to=to_addr,
        subject=reply_subject,
        body=body,
        in_reply_to=msg_id,
        references=msg_id,
        x_brogi_auto="reply",
    )

    # Vyčistit pending
    try:
        conn = get_conn(); cur = conn.cursor()
        cur.execute("DELETE FROM tg_pending_replies WHERE chat_id=%s", (chat_id,))
        conn.commit(); cur.close(); conn.close()
    except Exception:
        pass

    if ok:
        # DB update — email ZPRACOVANÝ + IMAP HOTOVO
        try:
            conn = get_conn(); cur = conn.cursor()
            cur.execute(
                "UPDATE email_messages SET task_status='HOTOVO', human_reviewed=TRUE, status='ZPRACOVANÝ' WHERE id=%s",
                (email_id,)
            )
            conn.commit(); cur.close(); conn.close()
        except Exception as e:
            log.error(f"reply DB update: {e}")
        try:
            from imap_actions import move_to_brogi_folder
            move_to_brogi_folder(email_id, "HOTOVO")
        except Exception as e:
            log.warning(f"reply IMAP move HOTOVO: {e}")
        send(f"✉️ <b>Reply odeslán</b> → <code>{to_addr}</code>\n<i>{len(text)} znaků</i>")
    else:
        send(f"⚠️ <b>Reply selhalo</b>: <code>{err or ''}</code>")


def process_callback(update: dict):
    # M1 final: text message → handler pro pending reply
    msg = update.get("message")
    if msg and (msg.get("text") or "").strip():
        try:
            _process_text_message(msg)
        except Exception as e:
            log.error(f"process_text_message failed: {e}")
        return

    cb = update.get("callback_query")
    if not cb:
        return
    data = cb.get("data", "")
    cb_id = cb["id"]
    parts = data.split(":")

    if parts[0] == "spam" and len(parts) >= 3:
        is_spam = parts[1] == "yes"
        email_id = parts[2]
        from_addr = _get_email_from(email_id)
        _mark_spam(email_id, is_spam, from_addr)
        label = "🗑 Označeno jako SPAM" if is_spam else "✅ Není spam — uloženo"
        answer_callback(cb_id, label)
        send(label + (f"\n<code>{from_addr}</code>" if from_addr else ""))
        log.info(f"Callback spam:{is_spam} email_id={email_id} from={from_addr}")

    elif parts[0] == "email" and len(parts) >= 3:
        action = parts[1]
        email_id = parts[2]
        email_action(email_id, action)
        label = ACTION_LABEL.get(action, "OK")
        answer_callback(cb_id, label)
        log.info(f"Callback email:{action} id={email_id}")
        # M2: po reverzibilní akci přidat ↶ Vrátit (1h) button
        if action in UNDO_REVERSIBLE:
            try:
                send(
                    f"{label}\n<i>Akci lze vrátit do 1h.</i>",
                    buttons=[[{"text": "↶ Vrátit (1h)", "callback_data": f"email:undo:{email_id}"}]],
                )
            except Exception as _e:
                log.warning(f"undo button send failed: {_e}")

    else:
        answer_callback(cb_id, "OK")


def run_callback_loop():
    offset = _load_offset()
    log.info(f"Telegram callback loop START (offset={offset})")
    while True:
        try:
            updates = get_updates(offset=offset)
            for u in updates:
                offset = u["update_id"] + 1
                _save_offset(offset)
                try:
                    process_callback(u)
                except Exception as e:
                    log.error(f"process_callback failed update_id={u.get('update_id')}: {e}")
            time.sleep(2)
        except BaseException as e:
            log.error(f"Callback loop iter error (continuing): {e!r}")
            time.sleep(5)

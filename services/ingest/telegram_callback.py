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


def process_callback(update: dict):
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

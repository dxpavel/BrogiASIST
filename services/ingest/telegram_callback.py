"""
BrogiASIST — Telegram callback handler (polling smyčka)
Zpracovává kliknutí na inline tlačítka od Pavla.
"""
import logging
import time
from db import get_conn
from telegram_notify import get_updates, answer_callback, send, delete_message
from imap_actions import action_done, move_to_trash, move_to_brogi_folder
from chroma_client import store_email_action

log = logging.getLogger(__name__)

_offset = 0


def _mark_spam(email_id: int, is_spam: bool, from_address: str = None):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE email_messages SET is_spam=%s, human_reviewed=TRUE, status='reviewed' WHERE id=%s",
        (is_spam, email_id)
    )
    if from_address:
        cur.execute("""
            INSERT INTO classification_rules (rule_type, match_field, match_value, result_value)
            VALUES ('spam', 'from_address', %s, %s)
            ON CONFLICT (rule_type, match_field, match_value) DO UPDATE
                SET result_value=EXCLUDED.result_value,
                    hit_count=classification_rules.hit_count + 1,
                    updated_at=NOW()
        """, (from_address, 'yes' if is_spam else 'no'))
    conn.commit()
    cur.close()
    conn.close()


def _get_email_from(email_id: int) -> str | None:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT from_address FROM email_messages WHERE id=%s", (email_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return row[0] if row else None


TYP_FOLDER = {
    "NOTIFIKACE": "NOTIFIKACE",
    "NEWSLETTER": "NEWSLETTER",
    "ESHOP":      "ESHOP",
}


def _folder_for_email(email_id: str) -> str:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT typ FROM email_messages WHERE id=%s", (email_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return TYP_FOLDER.get((row[0] or "") if row else "", "HOTOVO")


def _email_action(email_id: str, action: str):
    conn = get_conn()
    cur = conn.cursor()
    do_mark_read = True  # vždy označit přečtené, kromě skip

    if action == "hotovo":
        cur.execute("UPDATE email_messages SET task_status='HOTOVO', human_reviewed=TRUE, status='reviewed' WHERE id=%s", (email_id,))
        move_to_brogi_folder(email_id, "HOTOVO")
    elif action == "precteno":
        cur.execute("UPDATE email_messages SET task_status='HOTOVO', human_reviewed=TRUE, status='reviewed' WHERE id=%s", (email_id,))
        folder = _folder_for_email(email_id)
        move_to_brogi_folder(email_id, folder)
    elif action == "ceka":
        cur.execute("UPDATE email_messages SET task_status='ČEKÁ-NA-MĚ', human_reviewed=TRUE, status='reviewed' WHERE id=%s", (email_id,))
        move_to_brogi_folder(email_id, "CEKA")
        do_mark_read = False  # WAIT = zůstane unread
    elif action == "spam":
        from_addr = _get_email_from(email_id)
        _mark_spam(email_id, True, from_addr)
        move_to_trash(email_id)
    elif action == "of":
        cur.execute("SELECT subject, from_address FROM email_messages WHERE id=%s", (email_id,))
        row = cur.fetchone()
        if row:
            subject, from_addr = row
            import httpx as _httpx, os as _os
            bridge = _os.getenv("APPLE_BRIDGE_URL", "http://host.docker.internal:9100")
            try:
                _httpx.post(f"{bridge}/omnifocus/add_task", json={
                    "name": subject or "(bez předmětu)",
                    "note": f"Od: {from_addr}\nBrogiASIST email id: {email_id}",
                    "flagged": True
                }, timeout=15)
            except Exception as _e:
                log.error(f"OF bridge error: {_e}")
        cur.execute("UPDATE email_messages SET task_status='→OF', human_reviewed=TRUE, status='reviewed' WHERE id=%s", (email_id,))
        move_to_brogi_folder(email_id, "HOTOVO")
    elif action == "rem":
        cur.execute("SELECT subject, from_address FROM email_messages WHERE id=%s", (email_id,))
        row = cur.fetchone()
        if row:
            subject, from_addr = row
            import httpx as _httpx, os as _os
            bridge = _os.getenv("APPLE_BRIDGE_URL", "http://host.docker.internal:9100")
            try:
                _httpx.post(f"{bridge}/reminders/add", json={
                    "name": subject or "(bez předmětu)",
                    "body": f"Od: {from_addr}\nBrogiASIST email id: {email_id}",
                }, timeout=15)
            except Exception as _e:
                log.error(f"REM bridge error: {_e}")
        cur.execute("UPDATE email_messages SET task_status='→REM', human_reviewed=TRUE, status='reviewed' WHERE id=%s", (email_id,))
        move_to_brogi_folder(email_id, "HOTOVO")
    elif action == "note":
        cur.execute("SELECT subject, from_address, body_text FROM email_messages WHERE id=%s", (email_id,))
        row = cur.fetchone()
        if row:
            subject, from_addr, body = row
            import httpx as _httpx, os as _os
            bridge = _os.getenv("APPLE_BRIDGE_URL", "http://host.docker.internal:9100")
            try:
                _httpx.post(f"{bridge}/notes/add", json={
                    "name": subject or "(bez předmětu)",
                    "body": f"Od: {from_addr}\n\n{body or ''}"[:2000],
                }, timeout=15)
            except Exception as _e:
                log.error(f"NOTE bridge error: {_e}")
        cur.execute("UPDATE email_messages SET human_reviewed=TRUE, status='reviewed' WHERE id=%s", (email_id,))
        move_to_brogi_folder(email_id, "HOTOVO")
    elif action == "unsub":
        cur.execute("SELECT from_address FROM email_messages WHERE id=%s", (email_id,))
        row = cur.fetchone()
        if row:
            cur.execute("UPDATE email_messages SET is_spam=TRUE, human_reviewed=TRUE WHERE from_address=%s", (row[0],))
            cur.execute("""
                INSERT INTO classification_rules (rule_type, match_field, match_value, result_value)
                VALUES ('spam', 'from_address', %s, 'yes')
                ON CONFLICT (rule_type, match_field, match_value) DO UPDATE
                    SET result_value='yes', hit_count=classification_rules.hit_count+1, updated_at=NOW()
            """, (row[0],))
        move_to_trash(email_id)
    elif action == "skip":
        do_mark_read = False  # skip = nechej unread

    conn.commit()
    cur.close()
    conn.close()

    if do_mark_read:
        action_done(email_id)

    if action != "skip":
        # Ulož do ChromaDB pro učení
        try:
            conn2 = get_conn()
            cur2 = conn2.cursor()
            cur2.execute(
                "SELECT from_address, subject, body_text, typ, firma, mailbox FROM email_messages WHERE id=%s",
                (email_id,)
            )
            row = cur2.fetchone()
            cur2.close()
            conn2.close()
            if row:
                from_addr, subject, body, typ, firma, mailbox = row
                store_email_action(
                    str(email_id), from_addr or "", subject or "", body or "",
                    action, typ or "", firma or "", mailbox or ""
                )
        except Exception as _e:
            log.error(f"chroma store after action: {_e}")


ACTION_LABEL = {
    "hotovo":   "✅ Označeno jako hotovo",
    "precteno": "👁️ Označeno jako přečteno",
    "ceka":     "⏳ Čeká na mě",
    "spam":     "🗑️ Označeno jako SPAM",
    "of":       "📋 Přidáno do OmniFocus",
    "rem":      "⏰ Přidáno do Reminders",
    "note":     "📝 Uloženo do Notes",
    "unsub":    "🚫 Odhlášen odesílatel",
    "skip":     "⏭️ Přeskočeno",
}


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
        _email_action(email_id, action)
        label = ACTION_LABEL.get(action, "OK")
        answer_callback(cb_id, label)
        # Smaž TG zprávu s tlačítky
        try:
            conn = get_conn()
            cur = conn.cursor()
            cur.execute("SELECT tg_message_id FROM email_messages WHERE id=%s", (email_id,))
            row = cur.fetchone()
            cur.close()
            conn.close()
            if row and row[0]:
                delete_message(row[0])
        except Exception as _e:
            log.error(f"delete TG msg: {_e}")
        log.info(f"Callback email:{action} id={email_id}")

    else:
        answer_callback(cb_id, "OK")


def run_callback_loop():
    global _offset
    log.info("Telegram callback loop START")
    while True:
        try:
            updates = get_updates(offset=_offset)
            for u in updates:
                _offset = u["update_id"] + 1
                process_callback(u)
        except Exception as e:
            log.error(f"Callback loop: {e}")
        time.sleep(2)

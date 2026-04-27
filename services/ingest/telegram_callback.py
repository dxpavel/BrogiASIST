"""
BrogiASIST — Telegram callback handler (polling smyčka)
Zpracovává kliknutí na inline tlačítka od Pavla.
"""
import base64
import logging
import os
import time
from db import get_conn
from telegram_notify import get_updates, answer_callback, send, delete_message
from imap_actions import action_done, move_to_trash, move_to_brogi_folder
from chroma_client import store_email_action

log = logging.getLogger(__name__)

OFFSET_KEY = "tg_callback_offset"

# Limity pro base64 přenos příloh do Apple Bridge (POST JSON).
# Per-soubor 50 MB = stejné jako _MAX_ATTACHMENT_SIZE v ingest_email.py.
# Per-task 100 MB = horní strop pro celý OF task (rozumný JSON payload).
ATTACHMENT_MAX_SIZE  = 50 * 1024 * 1024
ATTACHMENT_TASK_MAX  = 100 * 1024 * 1024

# storage_path v DB může obsahovat:
#  - DEV: Mac cestu (bind mount /Users/pavel/Desktop/OmniFocus → /app/attachments) — nutno převést
#  - PROD: container cestu (žádný host overlay) — čte se přímo
# Řízeno env var ATTACHMENTS_HOST_PREFIX (DEV: "/Users/pavel/Desktop/OmniFocus", PROD: prázdné).
_HOST_PREFIX      = os.getenv("ATTACHMENTS_HOST_PREFIX", "")
_CONTAINER_PREFIX = "/app/attachments"


def _read_attachments_b64(file_paths: list[str], email_id: str) -> list[dict]:
    """Načte přílohy z disku, vrací list dictů {filename, content_base64, size_bytes}.

    Bere v úvahu per-file (50 MB) i per-task (100 MB) limit. Přesahující soubory
    přeskočí + zaloguje warning. Soubory mimo bind mount (neexistující) přeskočí
    bez chyby.
    """
    out: list[dict] = []
    total = 0
    for host_path in file_paths or []:
        if not host_path:
            continue
        # PROD: storage_path už je container path → použij přímo. DEV: replace host→container.
        cont_path = host_path.replace(_HOST_PREFIX, _CONTAINER_PREFIX, 1) if _HOST_PREFIX else host_path
        if not os.path.exists(cont_path):
            log.warning(f"OF attachment missing on disk: email_id={email_id} path={cont_path}")
            continue
        try:
            size = os.path.getsize(cont_path)
        except OSError as e:
            log.warning(f"OF attachment stat failed: email_id={email_id} {e}")
            continue
        if size > ATTACHMENT_MAX_SIZE:
            log.warning(f"OF attachment over {ATTACHMENT_MAX_SIZE//1024//1024} MB skipped: email_id={email_id} {cont_path} ({size} B)")
            continue
        if total + size > ATTACHMENT_TASK_MAX:
            log.warning(f"OF task attachments over {ATTACHMENT_TASK_MAX//1024//1024} MB total — skipping rest: email_id={email_id}")
            break
        try:
            with open(cont_path, "rb") as f:
                data = f.read()
        except OSError as e:
            log.warning(f"OF attachment read failed: email_id={email_id} {e}")
            continue
        out.append({
            "filename": os.path.basename(host_path),
            "content_base64": base64.b64encode(data).decode("ascii"),
            "size_bytes": size,
        })
        total += size
    if out:
        log.info(f"OF attachments prepared: email_id={email_id} count={len(out)} total_bytes={total}")
    return out


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


def _bridge_call(path: str, payload: dict, label: str, email_id: str) -> bool:
    """Volá Apple Bridge; vrací True pokud uspěl NEBO byl enqueue do pending_actions
    (degraded mode pro Apple Bridge offline — viz pending_worker.py).

    HTTP errory (4xx/5xx) → False + TG alert (server vrátil chybu, asi blbost v payload).
    Connection errory (timeout, refused) → enqueue + True (Bridge offline, akce čeká
    na drain worker, který ji zopakuje za < 1 min).
    """
    import httpx as _httpx, os as _os
    bridge = _os.getenv("APPLE_BRIDGE_URL", "http://host.docker.internal:9100")
    try:
        r = _httpx.post(f"{bridge}{path}", json=payload, timeout=15)
        if r.status_code == 200:
            log.info(f"{label} created: email_id={email_id} status=200")
            return True
        log.error(f"{label} FAILED: email_id={email_id} status={r.status_code} body={r.text[:200]}")
        try:
            send(f"❌ <b>{label} selhalo</b> ({r.status_code})\n<code>{r.text[:200]}</code>")
        except Exception:
            pass
        return False
    except (_httpx.ConnectError, _httpx.ConnectTimeout, _httpx.ReadTimeout, _httpx.NetworkError) as e:
        # Bridge unreachable — enqueue do pending_actions, drain worker to dorovná
        try:
            from pending_worker import enqueue
            pid = enqueue(str(email_id), label.lower(), path, payload)
            log.warning(f"{label} bridge offline → enqueued #{pid}: email_id={email_id} ({e})")
            try:
                send(f"⏳ <b>{label} ve frontě</b> (Apple Studio offline)\n<i>Pending #{pid} — proběhne automaticky až Bridge ožije.</i>")
            except Exception:
                pass
            return True
        except Exception as enq_err:
            log.error(f"{label} enqueue failed: email_id={email_id} {enq_err}")
            try:
                send(f"❌ <b>{label} selhalo + enqueue selhal</b>\n<code>{str(e)[:200]}</code>")
            except Exception:
                pass
            return False
    except Exception as e:
        log.error(f"{label} bridge error: email_id={email_id} {e}")
        try:
            send(f"❌ <b>{label} selhalo</b>\n<code>{str(e)[:200]}</code>")
        except Exception:
            pass
        return False


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
    "POZVÁNKA":   "POZVANKA",
}

# Mapování odesílatele → název Apple Calendar
_CAL_FROM_MAP = {
    "hrkel.ivan.hrkel@gmail.com": "PAJA",
    "mbank":                       "MBANK",   # substring match
}


def _calendar_for_email(from_addr: str) -> str:
    addr = (from_addr or "").lower()
    for key, cal in _CAL_FROM_MAP.items():
        if key in addr:
            return cal
    return "PAJA"


# České zkratky měsíců pro parsování předmětu pozvánky
_CZ_MONTHS = {
    "led": 1, "úno": 2, "bře": 3, "dub": 4, "kvě": 5, "čvn": 6,
    "čvc": 7, "srp": 8, "zář": 9, "říj": 10, "lis": 11, "pro": 12,
}


def _parse_invitation_subject(subject: str):
    """
    Parsuje předmět Google Calendar pozvánky.
    Formát: 'Invitation: NÁZEV @ [DEN] DD. MON YYYY [HH:MM] [- HH:MM] ...'
    Vrací (evt_name, start_iso_or_None, end_iso_or_None, all_day).
    """
    import re
    from datetime import datetime as dt, date as date_t

    # Název události (před @)
    name_m = re.match(r"(?:invitation|pozvánka):\s*(.+?)\s*@", subject, re.IGNORECASE)
    evt_name = name_m.group(1).strip() if name_m else subject

    # Datum + čas — hledej první výskyt 'DD. MON YYYY'
    pat = r"(\d{1,2})\.\s*(\w+)\s+(\d{4})(?:\s+(\d{1,2}):(\d{2}))?"
    m = re.search(pat, subject)
    if not m:
        return evt_name, None, None, True

    day = int(m.group(1))
    mon_str = m.group(2).lower()
    year = int(m.group(3))
    h_start = m.group(4)
    min_start = m.group(5)

    month = _CZ_MONTHS.get(mon_str)
    if not month:
        return evt_name, None, None, True

    if h_start:
        start = dt(year, month, day, int(h_start), int(min_start))
        # Hledej konecový čas '- HH:MM' po první hodině
        end_m = re.search(r"-\s*(\d{1,2}):(\d{2})", subject[m.end():m.end()+30])
        if end_m:
            end = dt(year, month, day, int(end_m.group(1)), int(end_m.group(2)))
        else:
            from datetime import timedelta
            end = start + timedelta(hours=1)
        return evt_name, start.isoformat(), end.isoformat(), False
    else:
        return evt_name, date_t(year, month, day).isoformat(), None, True


def _folder_for_email(email_id: str) -> str:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT typ FROM email_messages WHERE id=%s", (email_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return TYP_FOLDER.get((row[0] or "") if row else "", "HOTOVO")


def _email_action(email_id: str, action: str):
    """
    Pořadí: bridge call (pokud je) → DB UPDATE + COMMIT → IMAP move.
    DB se commituje DŘÍV než IMAP, jinak by druhá conn (uvnitř move_to_*)
    blokovala na row-locku této první conn.
    """
    do_mark_read = True  # vždy označit přečtené, kromě skip
    imap_op = None       # ("brogi", subfolder) | ("trash",) | None

    if action == "hotovo":
        conn = get_conn(); cur = conn.cursor()
        cur.execute("UPDATE email_messages SET task_status='HOTOVO', human_reviewed=TRUE, status='reviewed' WHERE id=%s", (email_id,))
        conn.commit(); cur.close(); conn.close()
        imap_op = ("brogi", "HOTOVO")
    elif action == "precteno":
        folder = _folder_for_email(email_id)
        conn = get_conn(); cur = conn.cursor()
        cur.execute("UPDATE email_messages SET task_status='HOTOVO', human_reviewed=TRUE, status='reviewed' WHERE id=%s", (email_id,))
        conn.commit(); cur.close(); conn.close()
        imap_op = ("brogi", folder)
    elif action == "ceka":
        conn = get_conn(); cur = conn.cursor()
        cur.execute("UPDATE email_messages SET task_status='ČEKÁ-NA-MĚ', human_reviewed=TRUE, status='reviewed' WHERE id=%s", (email_id,))
        conn.commit(); cur.close(); conn.close()
        imap_op = ("brogi", "CEKA")
        do_mark_read = False  # WAIT = zůstane unread
    elif action == "spam":
        from_addr = _get_email_from(email_id)
        _mark_spam(email_id, True, from_addr)
        imap_op = ("trash",)
    elif action == "del":
        # Jednorázové smazání bez učení sender=spam.
        # is_spam zůstává FALSE, classification_rules se NEpíše — Chroma
        # email_actions log (níž v _email_action) ale akci uloží, takže
        # find_repeat_action může 2del navrhnout pro podobný vzor příště.
        conn = get_conn(); cur = conn.cursor()
        cur.execute(
            "UPDATE email_messages SET human_reviewed=TRUE, status='reviewed' WHERE id=%s",
            (email_id,)
        )
        conn.commit(); cur.close(); conn.close()
        imap_op = ("trash",)
    elif action == "of":
        conn = get_conn(); cur = conn.cursor()
        cur.execute("SELECT subject, from_address, body_text FROM email_messages WHERE id=%s", (email_id,))
        row = cur.fetchone()
        if not row:
            cur.close(); conn.close(); return
        subject, from_addr, body_text = row
        # Přílohy: storage_path obsahuje Mac cestu, _read_attachments_b64
        # převede na kontejnerovou a načte do base64 (per-file 50 MB, per-task 100 MB).
        cur.execute(
            "SELECT storage_path FROM attachments WHERE source_type='email' AND source_record_id=%s::uuid ORDER BY filename",
            (email_id,)
        )
        file_paths = [r[0] for r in cur.fetchall()]
        cur.close(); conn.close()
        files_b64 = _read_attachments_b64(file_paths, str(email_id))
        body_preview = (body_text or "")[:1500].strip()
        note = f"Od: {from_addr}\n"
        if body_preview:
            note += f"\n{body_preview}\n"
        note += f"\n─────\nBrogiASIST id: {email_id}"
        ok = _bridge_call("/omnifocus/add_task", {
            "name": subject or "(bez předmětu)",
            "note": note,
            "flagged": True,
            "files": files_b64,
            "email_id": str(email_id),
        }, "OF", str(email_id))
        if not ok:
            return
        conn = get_conn(); cur = conn.cursor()
        cur.execute("UPDATE email_messages SET task_status='→OF', human_reviewed=TRUE, status='reviewed' WHERE id=%s", (email_id,))
        conn.commit(); cur.close(); conn.close()
        imap_op = ("brogi", "HOTOVO")
    elif action == "rem":
        conn = get_conn(); cur = conn.cursor()
        cur.execute("SELECT subject, from_address FROM email_messages WHERE id=%s", (email_id,))
        row = cur.fetchone()
        cur.close(); conn.close()
        if not row:
            return
        subject, from_addr = row
        ok = _bridge_call("/reminders/add", {
            "name": subject or "(bez předmětu)",
            "body": f"Od: {from_addr}\nBrogiASIST email id: {email_id}",
        }, "REM", str(email_id))
        if not ok:
            return
        conn = get_conn(); cur = conn.cursor()
        cur.execute("UPDATE email_messages SET task_status='→REM', human_reviewed=TRUE, status='reviewed' WHERE id=%s", (email_id,))
        conn.commit(); cur.close(); conn.close()
        imap_op = ("brogi", "HOTOVO")
    elif action == "note":
        conn = get_conn(); cur = conn.cursor()
        cur.execute("SELECT subject, from_address, body_text FROM email_messages WHERE id=%s", (email_id,))
        row = cur.fetchone()
        cur.close(); conn.close()
        if not row:
            return
        subject, from_addr, body = row
        ok = _bridge_call("/notes/add", {
            "name": subject or "(bez předmětu)",
            "body": f"Od: {from_addr}\n\n{body or ''}"[:2000],
        }, "NOTE", str(email_id))
        if not ok:
            return
        conn = get_conn(); cur = conn.cursor()
        cur.execute("UPDATE email_messages SET human_reviewed=TRUE, status='reviewed' WHERE id=%s", (email_id,))
        conn.commit(); cur.close(); conn.close()
        imap_op = ("brogi", "HOTOVO")
    elif action == "cal":
        conn = get_conn(); cur = conn.cursor()
        cur.execute("SELECT subject, from_address, body_text FROM email_messages WHERE id=%s", (email_id,))
        row = cur.fetchone()
        cur.close(); conn.close()
        if not row:
            return
        subject, from_addr, body = row
        cal_name = _calendar_for_email(from_addr)
        evt_name, start_iso, end_iso, all_day = _parse_invitation_subject(subject or "")
        ok = _bridge_call("/calendar/add", {
            "name": evt_name,
            "notes": f"Od: {from_addr}\n\n{body or ''}"[:1000],
            "calendar": cal_name,
            "start_iso": start_iso,
            "end_iso": end_iso,
            "all_day": all_day,
        }, "CAL", str(email_id))
        if not ok:
            return
        conn = get_conn(); cur = conn.cursor()
        cur.execute("UPDATE email_messages SET task_status='→CAL', human_reviewed=TRUE, status='reviewed' WHERE id=%s", (email_id,))
        conn.commit(); cur.close(); conn.close()
        imap_op = ("brogi", "HOTOVO")
    elif action == "unsub":
        conn = get_conn(); cur = conn.cursor()
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
        conn.commit(); cur.close(); conn.close()
        imap_op = ("trash",)
    elif action == "skip":
        do_mark_read = False  # skip = nechej unread

    if imap_op and imap_op[0] == "brogi":
        move_to_brogi_folder(email_id, imap_op[1])
    elif imap_op and imap_op[0] == "trash":
        move_to_trash(email_id)

    if do_mark_read:
        action_done(email_id)

    if action != "skip":
        try:
            conn2 = get_conn()
            cur2 = conn2.cursor()
            cur2.execute("""
                SELECT from_address, subject, body_text, typ, firma, mailbox,
                       ai_confidence, task_status
                FROM email_messages WHERE id=%s
            """, (email_id,))
            row = cur2.fetchone()
            cur2.close()
            conn2.close()
            if row:
                from_addr, subject, body, typ, firma, mailbox, ai_conf, task_st = row
                store_email_action(
                    str(email_id), from_addr or "", subject or "", body or "",
                    action, typ or "", firma or "", mailbox or "",
                    ai_confidence=ai_conf,
                    task_status=task_st or "",
                    human_corrected=True,
                )
        except Exception as _e:
            log.error(f"chroma store after action: {_e}")

    # Smaž TG zprávu s tlačítky (sjednoceně pro TG i WebUI cestu).
    try:
        conn3 = get_conn()
        cur3 = conn3.cursor()
        cur3.execute("SELECT tg_message_id FROM email_messages WHERE id=%s", (email_id,))
        row = cur3.fetchone()
        cur3.close()
        conn3.close()
        if row and row[0]:
            ok = delete_message(row[0])
            if ok:
                log.info(f"TG msg deleted: email_id={email_id} tg_msg_id={row[0]}")
            else:
                log.warning(f"TG msg delete failed (>48h or already gone): email_id={email_id} tg_msg_id={row[0]}")
    except Exception as _e:
        log.error(f"delete TG msg: {_e}")


ACTION_LABEL = {
    "hotovo":   "✅ Označeno jako hotovo",
    "precteno": "👁️ Označeno jako přečteno",
    "ceka":     "⏳ Čeká na mě",
    "spam":     "🚫 Označeno jako SPAM",
    "del":      "🗑️ Smazáno",
    "of":       "📋 Přidáno do OmniFocus",
    "rem":      "⏰ Přidáno do Reminders",
    "note":     "📝 Uloženo do Notes",
    "cal":      "📅 Přidáno do kalendáře",
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
        log.info(f"Callback email:{action} id={email_id}")

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

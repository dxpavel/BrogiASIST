"""
BrogiASIST — Email akce (sdílený modul, BUG-001 refactor 2026-05-04)

Sdílená business logika pro email akce — volaná z:
  - Telegram callback (telegram_callback.py:process_callback)
  - WebUI dashboard (api.py:apiemail_action)
  - (budoucí: iOS shortcut, hlasové ovládání, atd.)

Veřejná API:
  - email_action(email_id, action) — provede akci + zaznamená pro undo
  - email_undo(email_id)           — vrátí poslední akci (TTL 1h)
  - ACTION_LABEL                   — user-facing labels akcí
  - UNDO_REVERSIBLE                — set akcí které lze inverzovat

Privátní helpery (_underscore) — viz konec souboru.
"""
import base64
import logging
import os
from html import escape as escape_html
from db import get_conn
from telegram_notify import send, delete_message
from imap_actions import action_done, move_to_trash, move_to_brogi_folder
from chroma_client import store_email_action

log = logging.getLogger(__name__)

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



def _bridge_call(path: str, payload: dict, label: str, email_id: str) -> bool:
    """Volá Apple Bridge; vrací True pokud uspěl NEBO byl enqueue do pending_actions."""
    ok, _ = _bridge_call_full(path, payload, label, email_id)
    return ok


def _bridge_call_full(path: str, payload: dict, label: str, email_id: str) -> tuple[bool, dict | None]:
    """Stejné chování jako _bridge_call, ale navíc vrací parsed JSON odpověď
    (None pokud parse selže nebo byl enqueue/error).

    HTTP errory (4xx/5xx) → (False, None) + TG alert.
    Connection errory (timeout/refused) → (True, None) + enqueue do pending_actions.
    HTTP 200 → (True, dict) — volaný handler může vyčíst task_id apod.
    """
    import httpx as _httpx, os as _os
    bridge = _os.getenv("APPLE_BRIDGE_URL", "http://host.docker.internal:9100")
    # M2 undo: speciální payload {"_method": "DELETE"} → použít HTTP DELETE
    # (jinak default POST). Bridge má `@app.delete(...)` endpointy pro M2 undo.
    method = (payload.pop("_method", "POST") if isinstance(payload, dict) else "POST").upper()
    try:
        if method == "DELETE":
            r = _httpx.delete(f"{bridge}{path}", timeout=15)
        else:
            r = _httpx.post(f"{bridge}{path}", json=payload, timeout=15)
        if r.status_code == 200:
            log.info(f"{label} created: email_id={email_id} status=200")
            try:
                return True, r.json()
            except Exception:
                return True, None
        log.error(f"{label} FAILED: email_id={email_id} status={r.status_code} body={r.text[:200]}")
        try:
            send(f"❌ <b>{label} selhalo</b> ({r.status_code})\n<code>{r.text[:200]}</code>")
        except Exception:
            pass
        return False, None
    except (_httpx.ConnectError, _httpx.ConnectTimeout, _httpx.ReadTimeout, _httpx.NetworkError) as e:
        try:
            from pending_worker import enqueue
            pid = enqueue(str(email_id), label.lower(), path, payload)
            log.warning(f"{label} bridge offline → enqueued #{pid}: email_id={email_id} ({e})")
            try:
                send(f"⏳ <b>{label} ve frontě</b> (Apple Studio offline)\n<i>Pending #{pid} — proběhne automaticky až Bridge ožije.</i>")
            except Exception:
                pass
            return True, None
        except Exception as enq_err:
            log.error(f"{label} enqueue failed: email_id={email_id} {enq_err}")
            try:
                send(f"❌ <b>{label} selhalo + enqueue selhal</b>\n<code>{str(e)[:200]}</code>")
            except Exception:
                pass
            return False, None
    except Exception as e:
        log.error(f"{label} bridge error: email_id={email_id} {e}")
        try:
            send(f"❌ <b>{label} selhalo</b>\n<code>{str(e)[:200]}</code>")
        except Exception:
            pass
        return False, None


def _mark_spam(email_id: int, is_spam: bool, from_address: str = None):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE email_messages SET is_spam=%s, human_reviewed=TRUE, status=CASE WHEN %s THEN 'SMAZANÝ' ELSE 'ZPRACOVANÝ' END WHERE id=%s",
        (is_spam, is_spam, email_id)
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


# ===== M2: 2undo (TTL 1h) — vratitelnost poslední akce =====

UNDO_TTL_SECONDS = 3600  # 1h

# Akce které lze inverzovat. note/unsub/skip nelze (technický důvod).
# of/rem/cal: vyžadují DELETE endpointy v Apple Bridge (přidány 2026-05-04 v M2 final).
UNDO_REVERSIBLE = {"hotovo", "precteno", "ceka", "spam", "del", "of", "rem", "cal"}


def _capture_pre_action_state(email_id: str) -> dict:
    """Načte aktuální stav emailu PŘED akcí — payload pro budoucí reverzi."""
    try:
        conn = get_conn(); cur = conn.cursor()
        cur.execute("""
            SELECT folder, status, task_status, is_spam, of_task_id, rem_event_id, cal_event_id, from_address
            FROM email_messages WHERE id=%s
        """, (email_id,))
        row = cur.fetchone()
        cur.close(); conn.close()
        if not row:
            return {}
        return {
            "prev_folder": row[0],
            "prev_status": row[1],
            "prev_task_status": row[2],
            "prev_is_spam": row[3],
            "prev_of_task_id": row[4],
            "prev_rem_event_id": row[5],
            "prev_cal_event_id": row[6],
            "from_address": row[7],
        }
    except Exception as e:
        log.error(f"_capture_pre_action_state {email_id}: {e}")
        return {}


def _record_action(email_id: str, action: str, payload: dict):
    """Zapíše last_action + last_action_at + last_action_payload pro budoucí undo."""
    if action not in UNDO_REVERSIBLE:
        return
    try:
        import json as _json
        conn = get_conn(); cur = conn.cursor()
        cur.execute("""
            UPDATE email_messages
            SET last_action=%s, last_action_at=NOW(), last_action_payload=%s::jsonb
            WHERE id=%s
        """, (action, _json.dumps(payload, default=str), email_id))
        conn.commit(); cur.close(); conn.close()
    except Exception as e:
        log.error(f"_record_action {email_id} {action}: {e}")


def _folder_for_email(email_id: str) -> str:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT typ FROM email_messages WHERE id=%s", (email_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    return TYP_FOLDER.get((row[0] or "") if row else "", "HOTOVO")


def email_action(email_id: str, action: str):
    """
    Pořadí: bridge call (pokud je) → DB UPDATE + COMMIT → IMAP move.
    DB se commituje DŘÍV než IMAP, jinak by druhá conn (uvnitř move_to_*)
    blokovala na row-locku této první conn.
    """
    do_mark_read = True  # vždy označit přečtené, kromě skip
    imap_op = None       # ("brogi", subfolder) | ("trash",) | None

    # M2: undo support — capture state PŘED úpravou
    if action == "undo":
        return email_undo(email_id)
    pre_state = _capture_pre_action_state(email_id) if action in UNDO_REVERSIBLE else {}

    if action == "hotovo":
        conn = get_conn(); cur = conn.cursor()
        cur.execute("UPDATE email_messages SET task_status='HOTOVO', human_reviewed=TRUE, status='ZPRACOVANÝ' WHERE id=%s", (email_id,))
        conn.commit(); cur.close(); conn.close()
        imap_op = ("brogi", "HOTOVO")
    elif action == "precteno":
        folder = _folder_for_email(email_id)
        conn = get_conn(); cur = conn.cursor()
        cur.execute("UPDATE email_messages SET task_status='HOTOVO', human_reviewed=TRUE, status='ZPRACOVANÝ' WHERE id=%s", (email_id,))
        conn.commit(); cur.close(); conn.close()
        imap_op = ("brogi", folder)
    elif action == "ceka":
        conn = get_conn(); cur = conn.cursor()
        cur.execute("UPDATE email_messages SET task_status='ČEKÁ-NA-MĚ', human_reviewed=TRUE, status='ZPRACOVANÝ' WHERE id=%s", (email_id,))
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
        # email_actions log (níž v email_action) ale akci uloží, takže
        # find_repeat_action může 2del navrhnout pro podobný vzor příště.
        conn = get_conn(); cur = conn.cursor()
        cur.execute(
            "UPDATE email_messages SET human_reviewed=TRUE, status='SMAZANÝ' WHERE id=%s",
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
        ok, resp = _bridge_call_full("/omnifocus/add_task", {
            "name": subject or "(bez předmětu)",
            "note": note,
            "flagged": True,
            "files": files_b64,
            "email_id": str(email_id),
        }, "OF", str(email_id))
        if not ok:
            return
        # H2: persist task_id pro threading detekci budoucích replies
        task_id = (resp or {}).get("task_id")
        conn = get_conn(); cur = conn.cursor()
        if task_id:
            cur.execute(
                "UPDATE email_messages SET task_status='→OF', of_task_id=%s, of_linked_at=NOW(), human_reviewed=TRUE, status='ZPRACOVANÝ' WHERE id=%s",
                (task_id, email_id),
            )
            log.info(f"OF task linked: email_id={email_id} of_task_id={task_id}")
        else:
            cur.execute(
                "UPDATE email_messages SET task_status='→OF', human_reviewed=TRUE, status='ZPRACOVANÝ' WHERE id=%s",
                (email_id,),
            )
            log.warning(f"OF task created ale Bridge nevrátil task_id (degraded mode?): email_id={email_id}")
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
        ok, resp = _bridge_call_full("/reminders/add", {
            "name": subject or "(bez předmětu)",
            "body": f"Od: {from_addr}\nBrogiASIST email id: {email_id}",
        }, "REM", str(email_id))
        if not ok:
            return
        # M2: zachytit reminder id pro budoucí undo
        rem_id = (resp or {}).get("id")
        conn = get_conn(); cur = conn.cursor()
        if rem_id:
            cur.execute(
                "UPDATE email_messages SET task_status='→REM', rem_event_id=%s, human_reviewed=TRUE, status='ZPRACOVANÝ' WHERE id=%s",
                (rem_id, email_id),
            )
        else:
            cur.execute("UPDATE email_messages SET task_status='→REM', human_reviewed=TRUE, status='ZPRACOVANÝ' WHERE id=%s", (email_id,))
            log.warning(f"REM created bez id (Bridge return), undo nebude fungovat: email_id={email_id}")
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
        cur.execute("UPDATE email_messages SET human_reviewed=TRUE, status='ZPRACOVANÝ' WHERE id=%s", (email_id,))
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
        ok, resp = _bridge_call_full("/calendar/add", {
            "name": evt_name,
            "notes": f"Od: {from_addr}\n\n{body or ''}"[:1000],
            "calendar": cal_name,
            "start_iso": start_iso,
            "end_iso": end_iso,
            "all_day": all_day,
        }, "CAL", str(email_id))
        if not ok:
            return
        # M2: zachytit event UID pro budoucí undo
        cal_uid = (resp or {}).get("id")
        conn = get_conn(); cur = conn.cursor()
        if cal_uid:
            cur.execute(
                "UPDATE email_messages SET task_status='→CAL', cal_event_id=%s, human_reviewed=TRUE, status='ZPRACOVANÝ' WHERE id=%s",
                (cal_uid, email_id),
            )
        else:
            cur.execute("UPDATE email_messages SET task_status='→CAL', human_reviewed=TRUE, status='ZPRACOVANÝ' WHERE id=%s", (email_id,))
            log.warning(f"CAL created bez UID (Bridge return), undo nebude fungovat: email_id={email_id}")
        conn.commit(); cur.close(); conn.close()
        imap_op = ("brogi", "HOTOVO")
    elif action == "unsub":
        # 2026-05-04: Graceful no-op pokud email nemá List-Unsubscribe header.
        # Univerzální 3×3 layout zobrazuje 2unsub vždy (9 buttons), takže Pavel
        # může kliknout i u personal/business emailů. Bez headeru = informativní
        # TG zpráva, žádná destruktivní akce.
        conn = get_conn(); cur = conn.cursor()
        cur.execute("SELECT from_address, unsubscribe_url FROM email_messages WHERE id=%s", (email_id,))
        row = cur.fetchone()
        cur.close(); conn.close()
        if not row:
            send("⚠️ Email nenalezen.")
            do_mark_read = False
            return
        from_addr, unsub_url = row
        if not unsub_url:
            send(
                "⚠️ <b>Nelze odhlásit</b>\n"
                "Email nemá <code>List-Unsubscribe</code> header.\n"
                "Pokud je to spam, použij <code>🚫 2spam</code>."
            )
            do_mark_read = False
            return
        conn = get_conn(); cur = conn.cursor()
        cur.execute("UPDATE email_messages SET is_spam=TRUE, human_reviewed=TRUE WHERE from_address=%s", (from_addr,))
        cur.execute("""
            INSERT INTO classification_rules (rule_type, match_field, match_value, result_value)
            VALUES ('spam', 'from_address', %s, 'yes')
            ON CONFLICT (rule_type, match_field, match_value) DO UPDATE
                SET result_value='yes', hit_count=classification_rules.hit_count+1, updated_at=NOW()
        """, (from_addr,))
        conn.commit(); cur.close(); conn.close()
        imap_op = ("trash",)
    elif action == "of_open":
        # H2 thread flow: pošle do TG omnifocus:// URL pro tap-to-open na iOS/macOS.
        conn = get_conn(); cur = conn.cursor()
        cur.execute("SELECT of_task_id, subject FROM email_messages WHERE id=%s", (email_id,))
        row = cur.fetchone()
        cur.close(); conn.close()
        if not row or not row[0]:
            send("⚠️ <b>OF task není v threadu</b> — žádný of_task_id.")
            do_mark_read = False
            return
        tid, subj = row
        send(f"📂 <b>Otevři OF task:</b>\n<a href=\"omnifocus:///task/{tid}\">{escape_html(subj or '(bez předmětu)')}</a>")
        # Žádný IMAP/DB update — Pavel jen otevírá, čte, sám rozhodne dál
        do_mark_read = False
    elif action == "of_append":
        # H2 thread flow: append k notes existujícího OF tasku z threadu.
        conn = get_conn(); cur = conn.cursor()
        cur.execute("""
            SELECT em.of_task_id, em.from_address, em.subject, em.body_text, em.sent_at
            FROM email_messages em WHERE em.id=%s
        """, (email_id,))
        row = cur.fetchone()
        if not row or not row[0]:
            cur.close(); conn.close()
            send("⚠️ <b>OF task není v threadu</b> — žádný of_task_id.")
            do_mark_read = False
            return
        tid, fa, subj, body, sent_at = row
        cur.close(); conn.close()
        excerpt = (body or "").strip()[:1500]
        ts = sent_at.strftime("%Y-%m-%d %H:%M") if sent_at else ""
        append_text = (
            f"─────\n"
            f"📨 Update z threadu ({ts})\n"
            f"Od: {fa}\n"
            f"Předmět: {subj}\n\n"
            f"{excerpt}"
        )
        ok = _bridge_call(f"/omnifocus/task/{tid}/append_note",
                          {"text": append_text}, "OF append", str(email_id))
        if not ok:
            return
        conn = get_conn(); cur = conn.cursor()
        cur.execute(
            "UPDATE email_messages SET task_status='→OF', of_task_id=%s, of_linked_at=NOW(), human_reviewed=TRUE, status='ZPRACOVANÝ' WHERE id=%s",
            (tid, email_id),
        )
        conn.commit(); cur.close(); conn.close()
        log.info(f"OF append: email_id={email_id} of_task_id={tid}")
        imap_op = ("brogi", "HOTOVO")
    elif action == "of_new":
        # H2 thread flow: ignoruj existující thread vazbu, založ úplně nový OF task
        # (re-use of action s upraveným task_status loggingem).
        return email_action(email_id, "of")
    elif action == "skip":
        do_mark_read = False  # skip = nechej unread

    if imap_op and imap_op[0] == "brogi":
        move_to_brogi_folder(email_id, imap_op[1])
    elif imap_op and imap_op[0] == "trash":
        move_to_trash(email_id)

    if do_mark_read:
        action_done(email_id)

    # M2: zaznamenat akci pro undo (TTL 1h check v email_undo)
    if action in UNDO_REVERSIBLE and pre_state:
        # doplním post-action ID-ka (of_task_id atd. už je v DB)
        try:
            conn_p = get_conn(); cur_p = conn_p.cursor()
            cur_p.execute("SELECT of_task_id, rem_event_id, cal_event_id FROM email_messages WHERE id=%s", (email_id,))
            row_p = cur_p.fetchone()
            cur_p.close(); conn_p.close()
            if row_p:
                pre_state["new_of_task_id"] = row_p[0]
                pre_state["new_rem_event_id"] = row_p[1]
                pre_state["new_cal_event_id"] = row_p[2]
        except Exception:
            pass
        _record_action(email_id, action, pre_state)

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


def email_undo(email_id: str):
    """M2: Vrátit poslední akci. TTL 1h. Reverze podle last_action + payload."""
    from datetime import datetime, timezone
    try:
        conn = get_conn(); cur = conn.cursor()
        cur.execute("""
            SELECT last_action, last_action_at, last_action_payload
            FROM email_messages WHERE id=%s
        """, (email_id,))
        row = cur.fetchone()
        cur.close(); conn.close()
    except Exception as e:
        log.error(f"undo: load last_action failed {email_id}: {e}")
        send(f"⚠️ Undo selhalo (DB error): {e}")
        return

    if not row or not row[0]:
        send("⚠️ Žádná akce k vrácení.")
        return

    last_action, last_action_at, payload = row
    payload = payload or {}

    # TTL check
    if last_action_at:
        age_s = (datetime.now(timezone.utc) - last_action_at).total_seconds()
        if age_s > UNDO_TTL_SECONDS:
            send(f"⚠️ Undo už není možné — akce starší než {UNDO_TTL_SECONDS // 60} min.")
            return

    log.info(f"undo: email_id={email_id} last_action={last_action} age={int(age_s)}s")

    # Dispatch reverze
    if last_action in ("hotovo", "precteno", "ceka"):
        # Vrátit task_status + IMAP zpět z BrogiASIST/* do INBOX
        prev_ts = payload.get("prev_task_status")
        prev_status = payload.get("prev_status") or "classified"
        try:
            conn = get_conn(); cur = conn.cursor()
            cur.execute(
                "UPDATE email_messages SET task_status=%s, status=%s, human_reviewed=FALSE WHERE id=%s",
                (prev_ts, prev_status, email_id),
            )
            conn.commit(); cur.close(); conn.close()
        except Exception as e:
            log.error(f"undo {last_action}: DB reset failed: {e}")
        # IMAP move zpět do INBOX
        try:
            move_to_brogi_folder(email_id, "INBOX")
        except Exception as e:
            log.error(f"undo {last_action}: IMAP move INBOX failed: {e}")

    elif last_action == "spam":
        # is_spam=FALSE + smazat sender z classification_rules + IMAP move z Trash do INBOX
        sender = payload.get("from_address")
        try:
            conn = get_conn(); cur = conn.cursor()
            cur.execute(
                "UPDATE email_messages SET is_spam=%s, human_reviewed=FALSE, status=%s WHERE id=%s",
                (payload.get("prev_is_spam", False), payload.get("prev_status") or "classified", email_id),
            )
            if sender:
                cur.execute("DELETE FROM classification_rules WHERE rule_type='spam' AND match_value=%s",
                            (sender.lower(),))
            conn.commit(); cur.close(); conn.close()
        except Exception as e:
            log.error(f"undo spam: DB cleanup failed: {e}")
        try:
            move_to_brogi_folder(email_id, "INBOX")
        except Exception as e:
            log.error(f"undo spam: IMAP move INBOX failed: {e}")

    elif last_action == "del":
        # IMAP move z Trash do INBOX, status reset
        try:
            conn = get_conn(); cur = conn.cursor()
            cur.execute(
                "UPDATE email_messages SET human_reviewed=FALSE, status=%s WHERE id=%s",
                (payload.get("prev_status") or "classified", email_id),
            )
            conn.commit(); cur.close(); conn.close()
        except Exception as e:
            log.error(f"undo del: DB reset failed: {e}")
        try:
            move_to_brogi_folder(email_id, "INBOX")
        except Exception as e:
            log.error(f"undo del: IMAP move INBOX failed: {e}")

    elif last_action == "of":
        of_id = payload.get("new_of_task_id") or payload.get("prev_of_task_id")
        if of_id:
            ok, _resp = _bridge_call_full(f"/omnifocus/task/{of_id}", {"_method": "DELETE"}, "OF-undo", email_id)
            if not ok:
                send(f"⚠️ OF task se nepodařilo smazat (id={of_id}). DB reset proběhne.")
        else:
            send("⚠️ OF task ID v payloadu chybí, smazat nelze. DB reset proběhne.")
        try:
            conn = get_conn(); cur = conn.cursor()
            cur.execute(
                "UPDATE email_messages SET task_status=%s, of_task_id=NULL, of_linked_at=NULL, "
                "human_reviewed=FALSE, status=%s WHERE id=%s",
                (payload.get("prev_task_status"), payload.get("prev_status") or "classified", email_id),
            )
            conn.commit(); cur.close(); conn.close()
        except Exception as e:
            log.error(f"undo of: DB reset failed: {e}")
        try:
            move_to_brogi_folder(email_id, "INBOX")
        except Exception as e:
            log.error(f"undo of: IMAP move INBOX failed: {e}")

    elif last_action == "rem":
        rem_id = payload.get("new_rem_event_id") or payload.get("prev_rem_event_id")
        if rem_id:
            ok, _resp = _bridge_call_full(f"/reminders/{rem_id}", {"_method": "DELETE"}, "REM-undo", email_id)
            if not ok:
                send(f"⚠️ Reminder se nepodařilo smazat (id={rem_id}). DB reset proběhne.")
        else:
            send("⚠️ Reminder ID v payloadu chybí. DB reset proběhne.")
        try:
            conn = get_conn(); cur = conn.cursor()
            cur.execute(
                "UPDATE email_messages SET task_status=%s, rem_event_id=NULL, "
                "human_reviewed=FALSE, status=%s WHERE id=%s",
                (payload.get("prev_task_status"), payload.get("prev_status") or "classified", email_id),
            )
            conn.commit(); cur.close(); conn.close()
        except Exception as e:
            log.error(f"undo rem: DB reset failed: {e}")
        try:
            move_to_brogi_folder(email_id, "INBOX")
        except Exception as e:
            log.error(f"undo rem: IMAP move INBOX failed: {e}")

    elif last_action == "cal":
        cal_id = payload.get("new_cal_event_id") or payload.get("prev_cal_event_id")
        if cal_id:
            ok, _resp = _bridge_call_full(f"/calendar/{cal_id}", {"_method": "DELETE"}, "CAL-undo", email_id)
            if not ok:
                send(f"⚠️ Calendar event se nepodařilo smazat (uid={cal_id}). DB reset proběhne.")
        else:
            send("⚠️ Calendar UID v payloadu chybí. DB reset proběhne.")
        try:
            conn = get_conn(); cur = conn.cursor()
            cur.execute(
                "UPDATE email_messages SET task_status=%s, cal_event_id=NULL, "
                "human_reviewed=FALSE, status=%s WHERE id=%s",
                (payload.get("prev_task_status"), payload.get("prev_status") or "classified", email_id),
            )
            conn.commit(); cur.close(); conn.close()
        except Exception as e:
            log.error(f"undo cal: DB reset failed: {e}")
        try:
            move_to_brogi_folder(email_id, "INBOX")
        except Exception as e:
            log.error(f"undo cal: IMAP move INBOX failed: {e}")

    else:
        send(f"⚠️ Akce '{last_action}' nelze vrátit.")
        return

    # Vyčistit last_action — undo není reverzibilní (žádný re-undo)
    try:
        conn = get_conn(); cur = conn.cursor()
        cur.execute("UPDATE email_messages SET last_action=NULL, last_action_at=NULL, last_action_payload='{}'::jsonb WHERE id=%s", (email_id,))
        conn.commit(); cur.close(); conn.close()
    except Exception:
        pass

    send(f"↶ Vráceno: <code>{last_action}</code>")
    log.info(f"undo OK: email_id={email_id} action={last_action}")


ACTION_LABEL = {
    "hotovo":    "✅ Označeno jako hotovo",
    "precteno":  "👁️ Označeno jako přečteno",
    "ceka":      "⏳ Čeká na mě",
    "spam":      "🚫 Označeno jako SPAM",
    "del":       "🗑️ Smazáno",
    "of":        "📋 Přidáno do OmniFocus",
    "rem":       "⏰ Přidáno do Reminders",
    "note":      "📝 Uloženo do Notes",
    "cal":       "📅 Přidáno do kalendáře",
    "unsub":     "🚫 Odhlášen odesílatel",
    "skip":      "⏭️ Přeskočeno",
    "of_open":   "📂 OF link odeslán",
    "of_append": "📎 Příloženo k OF tasku",
    "of_new":    "➕ Nový OF task (mimo thread)",
    "undo":      "↶ Vráceno",
}



"""
BrogiASIST — Telegram notifikace pro klasifikované emaily
Spouští se každých 2 min ze scheduleru.
"""
import logging
from html import escape
from db import get_conn
from telegram_notify import send
from chroma_client import find_repeat_action_with_score

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


# Mapování action → "2X" label (pro Chroma predikci v extra řádku).
_ACTION_2X = {
    "of": "2of", "rem": "2rem", "cal": "2cal", "note": "2note",
    "hotovo": "2hotovo", "del": "2del", "spam": "2spam",
    "unsub": "2unsub", "skip": "2skip", "precteno": "Otevřu sám",
}


def _buttons_for_typ(
    typ: str, email_id: str,
    has_unsubscribe: bool = False,
    suggested: dict | None = None,
) -> list:
    """Univerzální 3×3 layout pro všechny TYPy (Pavlovo rozhodnutí 2026-04-27).

    Callback_data zůstává `email:<action>:<id>` (backward compat).
    `2unsub` se ukáže jen když email má `List-Unsubscribe` header.
    `ENCRYPTED` má navíc extra řádek `👁 Otevřu sám` (action=precteno).

    `suggested = {"action": "of", "confidence_pct": 88}` (z Chroma
    `find_repeat_action_with_score`) → přidá extra řádek nahoře
    `⭐ Navrženo: 2of (88%) ⭐` (1 velké tlačítko, callback stejný jako
    odpovídající akce v 3×3) a v 3×3 přepíše label tlačítka na `⭐ 2X ⭐`.
    """
    eid = email_id
    sug_action = (suggested or {}).get("action")

    def lbl(default: str, action: str) -> str:
        """Pokud akce odpovídá predikci, obalí label hvězdičkami místo původní ikony."""
        if action == sug_action:
            return f"⭐ {_ACTION_2X.get(action, action)} ⭐"
        return default

    row2 = [_btn(lbl("📅 2cal", "cal"),    "cal",  eid),
            _btn(lbl("📝 2note", "note"), "note", eid)]
    if has_unsubscribe:
        row2.append(_btn(lbl("🚫 2unsub", "unsub"), "unsub", eid))

    universal = [
        [_btn(lbl("✅ 2hotovo", "hotovo"), "hotovo", eid),
         _btn(lbl("📥 2of",     "of"),     "of",     eid),
         _btn(lbl("⏰ 2rem",    "rem"),    "rem",    eid)],
        row2,
        [_btn(lbl("⏭ 2skip",   "skip"),   "skip",   eid),
         _btn(lbl("🗑 2del",    "del"),    "del",    eid),
         _btn(lbl("🚫 2spam",   "spam"),   "spam",   eid)],
    ]

    if typ == "ENCRYPTED":
        universal = [[_btn(lbl("👁 Otevřu sám", "precteno"), "precteno", eid)]] + universal

    # Extra řádek s návrhem (jen pokud predikce existuje a action je v universalu).
    if suggested and sug_action and sug_action in _ACTION_2X:
        pct = suggested.get("confidence_pct")
        pct_str = f" ({pct}%)" if pct is not None else ""
        suggest_row = [[_btn(
            f"⭐ Navrženo: {_ACTION_2X[sug_action]}{pct_str} ⭐",
            sug_action, eid,
        )]]
        return suggest_row + universal

    return universal


def _render_buttons(typ: str, email_id: str, has_unsubscribe: bool = False,
                    suggested: dict | None = None) -> list:
    """Backward-compat alias pro starší volání."""
    return _buttons_for_typ(typ, email_id, has_unsubscribe, suggested)


def _buttons_for_thread(email_id: str) -> list:
    """H2: tlačítka pro thread continuation (email v threadu s existing OF task).
    [📂 Otevřít OF] [📎 Append do OF]
    [➕ Nový task]  [⏭ Skip]
    """
    eid = email_id
    return [
        [_btn("📂 Otevřít OF", "of_open", eid),
         _btn("📎 Append",     "of_append", eid)],
        [_btn("➕ Nový task",   "of_new", eid),
         _btn("⏭ Skip",        "skip", eid)],
    ]


def notify_classified_emails():
    conn = get_conn()
    cur = conn.cursor()
    # H2: LEFT JOIN LATERAL hledá prior email v threadu s of_task_id.
    # Pokud existuje → email je pokračování existujícího OF tasku → speciální zpráva.
    cur.execute("""
        SELECT em.id, em.mailbox, em.from_address, em.subject, em.typ, em.firma,
               em.ai_confidence, em.body_text,
               em.raw_payload->'headers'->>'List-Unsubscribe' AS list_unsub,
               em.is_personal, em.force_tg_notify, em.matched_groups,
               thr.of_task_id, thr.prev_subject
        FROM email_messages em
        LEFT JOIN LATERAL (
            SELECT em2.of_task_id, em2.subject AS prev_subject
            FROM email_messages em2
            WHERE em2.thread_id = em.thread_id
              AND em2.of_task_id IS NOT NULL
              AND em2.id <> em.id
            ORDER BY em2.sent_at ASC
            LIMIT 1
        ) thr ON em.thread_id IS NOT NULL
        WHERE em.typ IS NOT NULL
          AND em.is_spam = FALSE
          AND em.tg_notified_at IS NULL
          AND em.typ NOT IN ('SPAM', 'ESHOP')
          AND em.human_reviewed = FALSE
        ORDER BY em.sent_at DESC
        LIMIT 20
    """)
    rows = cur.fetchall()

    for (email_id, mailbox, from_addr, subject, typ, firma, confidence, body, list_unsub,
         is_personal, force_tg_notify, matched_groups,
         thread_of_task_id, thread_prev_subject) in rows:
        icon = TYP_ICON.get(typ, "📧")
        conf_str = f"{int((confidence or 0)*100)}%" if confidence else "?"
        short_from = from_addr.split("<")[-1].rstrip(">") if "<" in (from_addr or "") else (from_addr or "?")
        mb = mailbox.split("@")[0] if mailbox else "?"

        # H2: thread continuation → speciální zpráva místo standardní per-TYP
        if thread_of_task_id:
            text = (
                f"🧵 <b>THREAD pokračování</b>\n"
                f"{icon} <b>{escape(typ)}</b>  <code>{escape(mb)}</code>\n"
                f"Od: <code>{escape(short_from)}</code>\n"
                f"Předmět: {escape(subject or '(bez předmětu)')}\n"
                f"⛓ Existující OF task: <i>{escape((thread_prev_subject or '')[:80])}</i>"
            )
            buttons = _buttons_for_thread(str(email_id))
            result = send(text, buttons)
            if result:
                msg_id = result.get("message_id")
                cur.execute("UPDATE email_messages SET tg_notified_at=NOW(), tg_message_id=%s WHERE id=%s", (msg_id, email_id))
                log.info(f"TG thread notify: typ={typ} id={email_id} of_task={thread_of_task_id}")
            else:
                log.warning(f"TG thread notify FAILED: id={email_id}")
            continue

        # Zkontroluj ChromaDB — opakující se vzor?
        # 2026-04-27: silent auto-apply VYPNUTÝ. Místo automatické akce
        # zobrazíme zvýrazněné tlačítko `⭐ Navrženo: 2X (NN%) ⭐` v TG zprávě
        # a Pavel potvrdí kliknutím. Důvod: dnešní incident s krouzecka@volny.cz
        # — auto-apply by mohl smazat legitimní email bez možnosti zásahu.
        suggested = None
        chroma_match = find_repeat_action_with_score(from_addr or "", subject or "", body or "")
        if chroma_match:
            sug_action, match_count, total = chroma_match
            pct = round(100 * match_count / max(total, 1))
            suggested = {"action": sug_action, "confidence_pct": pct}
            log.info(f"chroma suggest: action={sug_action} {match_count}/{total} ({pct}%) email_id={email_id}")

        # H3: VIP prefix + personal/group indikátory
        personal_mark = " 👤" if is_personal else ""
        prefix = "⭐ <b>VIP</b> ⭐\n" if force_tg_notify else ""
        text = (
            f"{prefix}"
            f"{icon} <b>{escape(typ)}</b>  <code>{escape(mb)}</code>  <i>{conf_str}</i>\n"
            f"Od: <code>{escape(short_from)}</code>{personal_mark}\n"
            f"Předmět: {escape(subject or '(bez předmětu)')}"
        )
        if firma:
            text += f"\nFirma: <b>{escape(firma)}</b>"
        if matched_groups:
            text += f"\n<i>👥 {escape(', '.join(matched_groups))}</i>"
        if suggested:
            text += f"\n<i>🔁 Z minulosti: tento vzor → {_ACTION_2X.get(suggested['action'], suggested['action'])} ({suggested['confidence_pct']}%)</i>"

        buttons = _render_buttons(typ, str(email_id),
                                  has_unsubscribe=bool(list_unsub),
                                  suggested=suggested)
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

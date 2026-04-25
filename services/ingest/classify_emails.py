"""
BrogiASIST — Email klasifikace přes Llama3.2 + pravidla
"""
import os
import json
import logging
import httpx
from db import get_conn
from telegram_notify import send_spam_check
from imap_actions import move_to_trash, move_to_brogi_folder, TYP_FOLDER

log = logging.getLogger(__name__)

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://host.docker.internal:11434")
MODEL = "llama3.2-vision:11b"
SPAM_AUTO_THRESHOLD = 0.92  # nad tímto skórem označíme spam automaticky

MAILBOX_TO_FIRMA = {
    "dxpavel@icloud.com":               "PRIVATE",
    "dxpavel@gmail.com":                "PRIVATE",
    "postapro@dxpavel.cz":              "PRIVATE",
    "padre@seznam.cz":                  "PRIVATE",
    "zamecnictvi.rozdalovice@gmail.com":"ZAMECNICTVI",
    "pavel@dxpsolutions.cz":            "DXPSOLUTIONS",
    "brogi@dxpsolutions.cz":            "DXPSOLUTIONS",
    "support@dxpsolutions.cz":          "DXPSOLUTIONS",
    "servicedesk@dxpsolutions.cz":      "DXPSOLUTIONS",
}

PROMPT_TEMPLATE = """Klasifikuj tento email. Vrať POUZE JSON bez komentářů.

Od: {from_addr}
Předmět: {subject}
Obsah (prvních 400 znaků): {body}

Vrať JSON:
{{
  "firma": "<DXPSOLUTIONS|MBANK|ZAMECNICTVI|PRIVATE>",
  "typ": "<SPAM|NABÍDKA|ÚKOL|INFO|FAKTURA|POTVRZENÍ|NEWSLETTER|NOTIFIKACE>",
  "task_status": "<ČEKÁ-NA-MĚ|ČEKÁ-NA-ODPOVĚĎ|null>",
  "is_spam": <true|false>,
  "confidence": <0.0-1.0>,
  "reason": "<1 věta proč>"
}}"""


def _check_rules(from_addr: str) -> dict | None:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT result_value FROM classification_rules
        WHERE rule_type='spam' AND match_field='from_address' AND match_value=%s
    """, (from_addr,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if row:
        return {"is_spam": row[0] == "yes", "confidence": 1.0, "source": "rule"}
    return None


def _llama_classify(from_addr: str, subject: str, body: str) -> dict | None:
    prompt = PROMPT_TEMPLATE.format(
        from_addr=from_addr or "",
        subject=subject or "",
        body=(body or "")[:400]
    )
    try:
        r = httpx.post(f"{OLLAMA_URL}/api/generate",
                       json={"model": MODEL, "prompt": prompt, "stream": False},
                       timeout=60)
        r.raise_for_status()
        text = r.json().get("response", "")
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            return json.loads(text[start:end])
    except Exception as e:
        log.error(f"Llama classify: {e}")
    return None


def classify_new_emails(limit: int = 20):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, mailbox, from_address, subject, raw_payload
        FROM email_messages
        WHERE human_reviewed = FALSE AND (firma IS NULL OR typ IS NULL)
        ORDER BY ingested_at DESC
        LIMIT %s
    """, (limit,))
    rows = cur.fetchall()
    cur.close()
    conn.close()

    log.info(f"Klasifikace: {len(rows)} emailů")
    for email_id, mailbox, from_addr, subject, payload in rows:
        try:
            # 1. Firma z mailboxu (deterministicky)
            firma = MAILBOX_TO_FIRMA.get(mailbox)
            # Detekce mBank z odesílatele
            if not firma and from_addr and "mbank" in from_addr.lower():
                firma = "MBANK"
            if not firma:
                firma = "PRIVATE"

            # 2. Spam pravidla (bez AI)
            rule = _check_rules(from_addr or "")
            if rule and rule["is_spam"]:
                _save_classification(email_id, firma, "SPAM", None, True, 1.0)
                move_to_trash(email_id)
                log.info(f"SPAM (pravidlo → trash): {from_addr}")
                continue

            # 3. Llama klasifikace
            body = ""
            if isinstance(payload, dict):
                body = payload.get("body_text") or payload.get("body", "") or ""
            result = _llama_classify(from_addr, subject, body)
            if not result:
                continue

            is_spam = result.get("is_spam", False)
            confidence = float(result.get("confidence", 0.5))
            typ = result.get("typ", "INFO")
            task_status = result.get("task_status")
            if task_status == "null":
                task_status = None

            _save_classification(email_id, firma, typ, task_status, is_spam, confidence)

            # 4. Spam handling
            if is_spam:
                if confidence >= SPAM_AUTO_THRESHOLD:
                    move_to_trash(email_id)
                    log.info(f"SPAM (auto trash, {confidence:.0%}): {subject}")
                else:
                    send_spam_check(str(email_id), from_addr or "", subject or "")
                    log.info(f"SPAM? (Telegram dotaz, {confidence:.0%}): {subject}")

            # 5. Auto-přesun organizačních typů ≥85%
            elif confidence >= 0.85 and typ in ("NOTIFIKACE", "ESHOP", "NEWSLETTER", "POTVRZENÍ", "FAKTURA"):
                subfolder = TYP_FOLDER.get(typ)
                if subfolder:
                    move_to_brogi_folder(email_id, subfolder)
                    log.info(f"AUTO-MOVE {typ} → BrogiASIST/{subfolder}: {subject}")

            log.info(f"Klasifikováno: firma={firma} typ={typ} spam={is_spam} ({confidence:.0%})")

        except Exception as e:
            log.error(f"classify {email_id}: {e}")


def _save_classification(email_id, firma, typ, task_status, is_spam, confidence):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        UPDATE email_messages SET
            firma=%s, typ=%s, task_status=%s,
            is_spam=%s, ai_confidence=%s, status='classified'
        WHERE id=%s
    """, (firma, typ, task_status, is_spam, confidence, email_id))
    conn.commit()
    cur.close()
    conn.close()

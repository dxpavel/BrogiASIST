"""
BrogiASIST — Email klasifikace přes Llama3.2 + Claude verifikace + pravidla
"""
import os
import re
import json
import logging
import httpx
from html import escape as html_escape
from db import get_conn
from telegram_notify import send_spam_check, send as tg_send
from imap_actions import move_to_trash, move_to_brogi_folder, TYP_FOLDER

log = logging.getLogger(__name__)

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://host.docker.internal:11434")
MODEL = "llama3.2-vision:11b"
SPAM_AUTO_THRESHOLD = 0.92  # nad tímto skórem označíme spam automaticky
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = "claude-haiku-4-5"  # rychlý+levný pro verifikaci spamu

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
  "typ": "<SPAM|NABÍDKA|ÚKOL|INFO|FAKTURA|POTVRZENÍ|NEWSLETTER|NOTIFIKACE|POZVÁNKA>",
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


def _extract_email(from_addr: str) -> str:
    """Extrahuje čistou emailovou adresu z řetězce 'Jméno <email>' nebo '<email>'."""
    m = re.search(r'<([^>]+)>', from_addr or '')
    if m:
        return m.group(1).lower().strip()
    return (from_addr or '').lower().strip()


def _is_contact(from_addr: str) -> bool:
    """
    Vrátí True pokud email odesílatele existuje v apple_contacts.
    Kontakt = nikdy auto-spam (pokud není manuálně přidán do spam pravidel).
    """
    email = _extract_email(from_addr)
    if not email:
        return False
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT 1 FROM apple_contacts
            WHERE EXISTS (
                SELECT 1 FROM jsonb_array_elements(emails) AS e
                WHERE lower(e->>'value') = %s
            )
            LIMIT 1
        """, (email,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        return bool(row)
    except Exception as e:
        log.error(f"_is_contact {email}: {e}")
        return False


def _claude_verify_spam(from_addr: str, subject: str, body: str) -> dict | None:
    """
    Druhý názor od Claude Haiku — voláme když Llama označí spam s nízkým confidence.
    Každý odesílatel se volá jen jednou — výsledek se cachuje v claude_sender_verdicts.
    Vrátí {"is_spam": bool, "reason": str} nebo None při chybě.
    """
    email = _extract_email(from_addr)

    # 1. Zkontroluj cache
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT is_spam, reason FROM claude_sender_verdicts WHERE email = %s", (email,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row:
            log.info(f"Claude cache hit: {email} → is_spam={row[0]}")
            return {"is_spam": row[0], "reason": row[1], "cached": True}
    except Exception as e:
        log.error(f"Claude cache read: {e}")

    # 2. Cache miss → zavolej API
    if not ANTHROPIC_API_KEY:
        log.warning("ANTHROPIC_API_KEY není nastaven, přeskakuji Claude verifikaci")
        return None

    prompt = f"""Rozhodni, zda je tento email SPAM nebo legitimní. Buď přísný ale spravedlivý.
Pokud je odesílatel člověk (ne robot/newsletter/marketing), odpověz is_spam=false.

Od: {from_addr or ''}
Předmět: {subject or ''}
Obsah (prvních 600 znaků): {(body or '')[:600]}

Vrať POUZE JSON (bez komentářů):
{{"is_spam": true/false, "reason": "1 věta"}}"""

    try:
        r = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": CLAUDE_MODEL,
                "max_tokens": 128,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=30,
        )
        r.raise_for_status()
        text = r.json()["content"][0]["text"]
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            result = json.loads(text[start:end])
            # 3. Ulož do cache
            try:
                conn = get_conn()
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO claude_sender_verdicts (email, is_spam, reason)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (email) DO UPDATE SET
                        is_spam = EXCLUDED.is_spam,
                        reason = EXCLUDED.reason,
                        verified_at = NOW()
                """, (email, result.get("is_spam", False), result.get("reason", "")))
                conn.commit()
                cur.close()
                conn.close()
                log.info(f"Claude verdict uložen: {email} → is_spam={result.get('is_spam')}")
            except Exception as e:
                log.error(f"Claude cache write: {e}")
            return result
    except Exception as e:
        log.error(f"Claude verify spam API: {e}")
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

            # 2a. Deterministická klasifikace pozvánky z kalendáře
            if subject and re.match(r'^invitation:', subject.strip(), re.IGNORECASE):
                _save_classification(email_id, firma, "POZVÁNKA", None, False, 1.0)
                log.info(f"POZVÁNKA (pravidlo): {subject[:60]}")
                continue

            # 2b. Spam pravidla — manuální override (nejvyšší priorita, i nad kontakty)
            rule = _check_rules(from_addr or "")
            if rule and rule["is_spam"]:
                _save_classification(email_id, firma, "SPAM", None, True, 1.0)
                move_to_trash(email_id)
                log.info(f"SPAM (pravidlo → trash): {from_addr}")
                continue

            # 2c. Kontakt v Apple Contacts → blokuje AI spam
            #     (pravidlo výše ho může přepsat — manuální spam > kontakt)
            in_contacts = _is_contact(from_addr or "")
            if in_contacts:
                log.info(f"KONTAKT whitelist (no-spam): {_extract_email(from_addr or '')}")

            # 3. Llama klasifikace
            body = ""
            if isinstance(payload, dict):
                body = payload.get("body_text") or payload.get("body", "") or ""
            result = _llama_classify(from_addr, subject, body)
            if not result:
                continue

            is_spam = result.get("is_spam", False)
            # Kontakt v adresáři → nikdy spam bez ohledu na AI
            if in_contacts and is_spam:
                log.info(f"KONTAKT override: AI řekla spam, ignoruji ({from_addr})")
                is_spam = False
            confidence = float(result.get("confidence", 0.5))
            typ = result.get("typ", "INFO")
            task_status = result.get("task_status")
            if task_status == "null":
                task_status = None

            _save_classification(email_id, firma, typ, task_status, is_spam, confidence)

            # 4. Spam handling
            if is_spam:
                short_from = _extract_email(from_addr or "")
                if confidence >= SPAM_AUTO_THRESHOLD:
                    move_to_trash(email_id)
                    tg_send(f"🗑️ <b>AUTO-SPAM</b> ({confidence:.0%})\n<code>{html_escape(short_from)}</code>\n<i>{html_escape((subject or '')[:80])}</i>")
                    log.info(f"SPAM (auto trash, {confidence:.0%}): {subject}")
                else:
                    # Llama není jistá → zeptáme se Claude
                    log.info(f"SPAM? Llama {confidence:.0%} → Claude verifikace: {subject[:60]}")
                    claude = _claude_verify_spam(from_addr or "", subject or "", body)
                    if claude is None:
                        # Claude nedostupný → fallback na TG
                        send_spam_check(str(email_id), from_addr or "", subject or "")
                        log.info(f"SPAM? (Claude chyba → TG, {confidence:.0%}): {subject}")
                    elif claude.get("is_spam"):
                        # Claude potvrdil spam → trash
                        _save_classification(email_id, firma, typ, task_status, True, confidence)
                        move_to_trash(email_id)
                        cached = " (cache)" if claude.get("cached") else ""
                        tg_send(f"🗑️ <b>AUTO-SPAM</b> Claude{cached} ({confidence:.0%})\n<code>{html_escape(short_from)}</code>\n<i>{html_escape((subject or '')[:80])}</i>")
                        log.info(f"SPAM (Claude potvrzen → trash, {confidence:.0%}): {claude.get('reason','')}")
                    else:
                        # Claude říká NENÍ spam → překlasifikuj a nech projít normálně
                        _save_classification(email_id, firma, typ, task_status, False, confidence)
                        log.info(f"SPAM zamítnut Claudem ({confidence:.0%}): {claude.get('reason','')} | {from_addr}")

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

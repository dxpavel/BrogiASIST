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
from decision_engine import evaluate_email

log = logging.getLogger(__name__)

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://host.docker.internal:11434")
MODEL = "llama3.2-vision:11b"
# Auto-spam je dočasně VYPNUTÝ (2026-04-27, threshold > 1.0 = nikdy true).
# Důvod: race condition — log produkoval `SPAM (auto trash, 100%)` ale zároveň
# v stejném tiku `Klasifikováno: typ=ÚKOL spam=false` (case: krouzecka@volny.cz,
# email 139b0c88, dane 2025 od účetní). Email byl auto-přesunut do Trash
# přes IMAP, ale finální DB rozhodnutí bylo spam=false → nesoulad.
# Dokud root cause nenajdeme, ZADNY auto-spam — Pavel klikne 2spam/2del ručně
# na TG. Učení v Chromě email_actions dál funguje, jen bez auto-execute.
SPAM_AUTO_THRESHOLD = 2.0
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
Obsah (prvních 500 znaků): {body}

Vrať JSON:
{{
  "firma": "<DXPSOLUTIONS|MBANK|ZAMECNICTVI|PRIVATE>",
  "typ": "<ÚKOL|DOKLAD|NABÍDKA|NOTIFIKACE|POZVÁNKA|INFO>",
  "task_status": "<ČEKÁ-NA-ODPOVĚĎ|null>",
  "is_spam": <true|false>,
  "confidence": <0.0-1.0>,
  "reason": "<1 věta proč>"
}}

Pravidla pro TYP (per spec brogiasist-semantics-v1):
- ÚKOL: někdo na mě v obsahu čeká nebo ode mě něco očekává
- DOKLAD: faktura, výpis, objednávka, paragon, formální papírová stopa
- NABÍDKA: komerční sdělení (kup si, sleva, akce)
- NOTIFIKACE: systém/služba mě informuje o události (vč. potvrzení objednávky, login alertů)
- POZVÁNKA: Calendar invite (subject 'Invitation:' nebo .ics)
- INFO: vše ostatní informativní (newsletter, blog update, OOO reply)

Pravidla pro task_status (Pavlovo rozhodnutí 2026-05-04):
- "ČEKÁ-NA-MĚ" se NIKDY nepoužívá — TYP=ÚKOL už sám říká „čeká na mě", je to redundantní
- "ČEKÁ-NA-ODPOVĚĎ" jen když Pavel poslal dotaz/email a čeká odpověď od někoho třetího
- null v ostatních případech (vč. INFO, NOTIFIKACE, NABÍDKA bez follow-upu)

POZNÁMKA: TYPy ERROR (bounce/DSN), LIST (mailing list), ENCRYPTED (S/MIME) detekuje
header check v decision_rules engine PŘED Llamou — sem nepřijdou."""

# Whitelist hodnot pro validaci Llama outputu (sanitizace placeholder strings).
_VALID_TYP = {"ÚKOL", "DOKLAD", "NABÍDKA", "NOTIFIKACE", "POZVÁNKA", "INFO"}
_VALID_TASK_STATUS = {"ČEKÁ-NA-ODPOVĚĎ", "HOTOVO", "→OF", "→REM", "→CAL"}
_VALID_FIRMA = {"DXPSOLUTIONS", "MBANK", "ZAMECNICTVI", "PRIVATE"}


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

            # Body extrakce — potřebné pro decision engine i Llamu
            body = ""
            if isinstance(payload, dict):
                body = payload.get("body_text") or payload.get("body", "") or ""

            # 1.5. Decision engine — konfigurovatelná pravidla z DB
            #      (header check, group match, chroma vzor, AI fallback)
            try:
                decision = evaluate_email({
                    "from_address": from_addr,
                    "subject": subject,
                    "raw_payload": payload,
                    "body_text": body,
                })
            except Exception as e:
                log.warning(f"decision_engine failed: {e}")
                decision = {"end_pipeline": False, "skip": False, "matched_rules": []}

            # Bot vlastní reply (X-Brogi-Auto header) → neklasifikujeme
            if decision.get("skip"):
                log.info(f"Decision skip: rules={decision.get('matched_rules')}")
                continue

            # Pravidlo dalo finální TYP (LIST, ENCRYPTED, INFO/OOO, ERROR/bounce)
            if decision.get("end_pipeline") and decision.get("typ"):
                rule_typ = decision["typ"]
                _save_classification(email_id, firma, rule_typ, None, False, 1.0)
                _save_decision_flags(email_id, decision)
                log.info(f"Decision: TYP={rule_typ} via rules={decision.get('matched_rules')}")
                continue

            # Chroma vzor — aplikuj zapamatovanou akci místo AI
            if decision.get("remembered_action"):
                ra_action = (decision.get("remembered_action") or {}).get("action")
                log.info(f"Decision: chroma vzor → action={ra_action} (TODO: action-wiring v blockeru D)")
                # Pro teď pokračujeme na AI; full action-wiring přijde v D

            # H3: persist flagy (is_personal/force_tg_notify/no_auto_*/matched_*)
            # do DB i pro Llama-klasifikované emaily — notify_emails je čte
            # pro visual indikátory (👤, ⭐ VIP, 👥 groups) a no_auto_action
            # pro skip auto-trash níže.

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

            # 3. Llama klasifikace (body už je extrahované z bodu 1)
            result = _llama_classify(from_addr, subject, body)
            if not result:
                continue

            is_spam = result.get("is_spam", False)
            # Kontakt v adresáři → nikdy spam bez ohledu na AI
            if in_contacts and is_spam:
                log.info(f"KONTAKT override: AI řekla spam, ignoruji ({from_addr})")
                is_spam = False
            confidence = float(result.get("confidence", 0.5))
            # 2026-05-04: Sanitize Llama output — invalid hodnoty (vč. raw
            # placeholder stringů typu "<ÚKOL|DOKLAD|...>") → fallback.
            raw_typ = result.get("typ", "INFO")
            typ = raw_typ if raw_typ in _VALID_TYP else "INFO"
            if typ != raw_typ:
                log.warning(f"Llama vrátila invalid typ={raw_typ!r}, fallback INFO ({email_id})")

            raw_status = result.get("task_status")
            if raw_status in (None, "null", "", "<ČEKÁ-NA-ODPOVĚĎ|null>"):
                task_status = None
            elif raw_status == "ČEKÁ-NA-MĚ":
                # Pavlovo pravidlo: ČEKÁ-NA-MĚ je redundantní s TYP=ÚKOL → null
                task_status = None
                log.info(f"task_status='ČEKÁ-NA-MĚ' ignorováno (redundant s ÚKOL): {email_id}")
            elif raw_status in _VALID_TASK_STATUS:
                task_status = raw_status
            else:
                log.warning(f"Llama vrátila invalid task_status={raw_status!r}, fallback null ({email_id})")
                task_status = None

            # Cross-rule: task_status='ČEKÁ-NA-ODPOVĚĎ' nedává smysl pro
            # NEWSLETTER/INFO (nikdy se neodpovídá) — fallback na null.
            if task_status == "ČEKÁ-NA-ODPOVĚĎ" and typ in ("INFO", "NEWSLETTER", "NOTIFIKACE"):
                log.info(f"task_status='ČEKÁ-NA-ODPOVĚĎ' s typ={typ} → null: {email_id}")
                task_status = None

            _save_classification(email_id, firma, typ, task_status, is_spam, confidence)
            _save_decision_flags(email_id, decision)

            # 4. Spam handling
            if is_spam:
                short_from = _extract_email(from_addr or "")
                # H3: no_auto_action flag (např. VIP rule) → vždy ručně, i když AI 99%
                no_auto = bool(decision.get("no_auto_action"))
                if confidence >= SPAM_AUTO_THRESHOLD and not no_auto:
                    move_to_trash(email_id)
                    tg_send(f"🗑️ <b>AUTO-SPAM</b> ({confidence:.0%})\n<code>{html_escape(short_from)}</code>\n<i>{html_escape((subject or '')[:80])}</i>")
                    log.info(f"SPAM (auto trash, {confidence:.0%}): {subject}")
                elif no_auto and confidence >= SPAM_AUTO_THRESHOLD:
                    # Flag přebíjí auto-trash → nech rozhodnout Pavla přes TG
                    send_spam_check(str(email_id), from_addr or "", subject or "")
                    log.info(f"SPAM (no_auto_action override → TG, {confidence:.0%}): {subject}")
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
                        tg_send(f"🗑️ <b>AUTO-SPAM</b> Claude potvrdil{cached}\n<code>{html_escape(short_from)}</code>\n<i>{html_escape((subject or '')[:80])}</i>")
                        log.info(f"SPAM (Claude potvrzen → trash, Llama {confidence:.0%}): {claude.get('reason','')}")
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


def _save_decision_flags(email_id, decision: dict):
    """Persist decision_engine flagy + matched_rules/groups do email_messages.
    Volá se po každém evaluate_email() — i když rule jen flagovalo.
    """
    if not decision:
        return
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            UPDATE email_messages SET
                is_personal           = %s,
                force_tg_notify       = %s,
                no_auto_action        = %s,
                no_auto_konstruktivni = %s,
                matched_rules         = %s,
                matched_groups        = %s
            WHERE id=%s
        """, (
            bool(decision.get("is_personal")),
            bool(decision.get("force_tg_notify")),
            bool(decision.get("no_auto_action")),
            bool(decision.get("no_auto_konstruktivni")),
            decision.get("matched_rules") or None,
            decision.get("matched_groups") or None,
            email_id,
        ))
        conn.commit()
    finally:
        cur.close()
        conn.close()

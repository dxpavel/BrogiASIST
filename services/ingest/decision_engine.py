"""
Decision engine — konfigurovatelný rozhodovací stroj pro email klasifikaci.

Volá se v classify_emails PŘED AI Llamou. Načte pravidla z DB tabulky
decision_rules (priority ASC), aplikuje je proti emailu, vrátí decision dict.

Per docs/brogiasist-semantics-v1.md sekce 5–6.

Pravidla jsou konfigurovatelná z WebUI bez deploye (TODO: editor v dashboardu).
"""

import json
import re
import logging
from typing import Optional
from db import get_conn

logger = logging.getLogger(__name__)


def load_rules(conn=None) -> list[dict]:
    """Vrátí enabled pravidla seřazená dle priority ASC."""
    own_conn = conn is None
    if own_conn:
        conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT priority, rule_name, condition_type, condition_value,
               action_type, action_value
        FROM decision_rules
        WHERE enabled = TRUE
        ORDER BY priority ASC
    """)
    rules = []
    for r in cur.fetchall():
        rules.append({
            "priority": r[0],
            "rule_name": r[1],
            "condition_type": r[2],
            "condition_value": r[3] or {},
            "action_type": r[4],
            "action_value": r[5] or {},
        })
    cur.close()
    if own_conn:
        conn.close()
    return rules


# ---------- Helpers ----------

def _extract_email_addr(from_address: str) -> Optional[str]:
    """Extrahuje plain email z 'Name <email@x.com>' nebo 'email@x.com'."""
    if not from_address:
        return None
    m = re.search(r'<([^>]+@[^>]+)>', from_address)
    if m:
        return m.group(1).strip().lower()
    m = re.search(r'(\S+@\S+\.\S+)', from_address)
    if m:
        return m.group(1).strip().lower().rstrip('.,;>')
    return None


def _get_headers(email: dict) -> dict:
    """raw_payload může být str (JSON) nebo už parsed dict."""
    raw = email.get("raw_payload") or {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except Exception:
            return {}
    return raw.get("headers") or {}


# ---------- Condition evaluators ----------

def _eval_header(condition: dict, email: dict) -> bool:
    name = condition.get("header")
    op = condition.get("operator", "exists")
    expected = str(condition.get("value", "")).lower()
    headers = _get_headers(email)
    actual = headers.get(name)
    if actual is None:
        return False
    if op == "exists":
        return True
    actual_l = str(actual).lower()
    if op == "equals":
        return actual_l == expected
    if op == "contains":
        return expected in actual_l
    if op == "startswith":
        return actual_l.startswith(expected)
    return False


def _eval_group(condition: dict, email: dict, conn) -> tuple[bool, list[str]]:
    """(matched?, list_of_intersecting_groups)"""
    target = set(condition.get("groups", []))
    if not target:
        return False, []
    addr = _extract_email_addr(email.get("from_address", ""))
    if not addr:
        return False, []
    cur = conn.cursor()
    try:
        # Case-insensitive match přes jsonb_path_query: emails uložené v Apple
        # Contacts mají různý casing (Koscusko@seznam.cz vs koscusko@seznam.cz),
        # pure jsonb @> by selhal. Porovnáváme lower(value) == lower(addr).
        cur.execute("""
            SELECT groups FROM apple_contacts
            WHERE EXISTS (
                SELECT 1 FROM jsonb_array_elements(emails) AS e
                WHERE lower(e->>'value') = lower(%s)
            )
              AND jsonb_array_length(groups) > 0
            LIMIT 1
        """, (addr,))
        row = cur.fetchone()
    finally:
        cur.close()
    if not row or not row[0]:
        return False, []
    sender_groups = set(row[0])
    matched = sender_groups & target
    return bool(matched), sorted(matched)


def _eval_sender(condition: dict, email: dict) -> bool:
    expected = str(condition.get("email", "")).lower().strip()
    actual = _extract_email_addr(email.get("from_address", ""))
    return bool(actual) and actual == expected


def _eval_chroma(condition: dict, email: dict) -> Optional[dict]:
    """Vrací zapamatovanou action z Chromy pokud je podobná, jinak None.

    chroma_client.find_repeat_action(from_addr, subject, body) → str | None
    Vrací jen action name (např. 'spam', 'hotovo') — threshold je interní.
    """
    try:
        from chroma_client import find_repeat_action  # type: ignore
    except ImportError:
        return None
    try:
        action = find_repeat_action(
            email.get("from_address", "") or "",
            email.get("subject", "") or "",
            email.get("body_text", "") or "",
        )
        if action:
            return {"action": action}
        return None
    except Exception as e:
        logger.warning(f"chroma eval failed: {e}")
        return None


# ---------- Main ----------

def evaluate_email(email: dict, conn=None) -> dict:
    """Vrátí decision dict popisující jak naložit s emailem.

    Klíče (vždy přítomné, bezpečné default hodnoty):
      typ, action, status                — set hodnoty pro klasifikaci
      skip                               — přeskočit úplně (bot reply)
      force_tg_notify                    — vždy notifikovat (VIP)
      no_auto_action                     — neprovádět žádnou auto-action
      is_personal                        — flag pro AI prompt
      no_auto_konstruktivni              — povolit jen 2spam/2hotovo/2skip
      remembered_action                  — dict z Chromy (pokud match)
      run_llama                          — explicit run AI
      end_pipeline                       — neprocházet další pravidla
      matched_rules                      — list rule_name pro audit
      matched_groups                     — list skupin co matchly
    """
    own_conn = conn is None
    if own_conn:
        conn = get_conn()

    decision = {
        "typ": None, "action": None, "status": None,
        "skip": False,
        "force_tg_notify": False, "no_auto_action": False,
        "is_personal": False, "no_auto_konstruktivni": False,
        "remembered_action": None,
        "run_llama": False,
        "end_pipeline": False,
        "matched_rules": [],
        "matched_groups": [],
    }

    try:
        rules = load_rules(conn)
    except Exception as e:
        logger.error(f"load_rules failed: {e}")
        decision["run_llama"] = True
        if own_conn:
            conn.close()
        return decision

    for rule in rules:
        ct = rule["condition_type"]
        cv = rule["condition_value"]
        at = rule["action_type"]
        av = rule["action_value"]
        rn = rule["rule_name"]

        matched = False
        extra: dict = {}
        try:
            if ct == "header":
                matched = _eval_header(cv, email)
            elif ct == "group":
                matched, groups = _eval_group(cv, email, conn)
                if matched:
                    extra["matched_groups"] = groups
            elif ct == "sender":
                matched = _eval_sender(cv, email)
            elif ct == "chroma":
                cr = _eval_chroma(cv, email)
                if cr is not None:
                    matched = True
                    extra["chroma_result"] = cr
            elif ct == "ai_fallback":
                matched = True
            else:
                logger.warning(f"rule {rn}: unknown condition_type {ct}")
        except Exception as e:
            logger.warning(f"rule {rn} eval failed: {e}")
            continue

        if not matched:
            continue

        decision["matched_rules"].append(rn)

        # Apply action
        if at == "end":
            if "typ" in av:    decision["typ"] = av["typ"]
            if "action" in av: decision["action"] = av["action"]
            if "status" in av: decision["status"] = av["status"]
            if av.get("skip"): decision["skip"] = True
            decision["end_pipeline"] = True
            break

        elif at == "flag":
            for k in ("force_tg_notify", "no_auto_action",
                      "is_personal", "no_auto_konstruktivni"):
                if av.get(k):
                    decision[k] = True
            if extra.get("matched_groups"):
                for g in extra["matched_groups"]:
                    if g not in decision["matched_groups"]:
                        decision["matched_groups"].append(g)
            # continue na další pravidlo

        elif at == "apply_remembered":
            cr = extra.get("chroma_result")
            if cr:
                decision["remembered_action"] = cr
                decision["action"] = cr.get("action")
                decision["end_pipeline"] = True
                break

        elif at == "run_llama":
            decision["run_llama"] = True
            break

        else:
            logger.warning(f"rule {rn}: unknown action_type {at}")

    if own_conn:
        conn.close()
    return decision

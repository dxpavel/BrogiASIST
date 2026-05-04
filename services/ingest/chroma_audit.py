"""
ChromaDB email_actions — read-only audit pro detekci optimalizačních příležitostí.

Per Pavlův dotaz 2026-04-26: zjistit zda v Chromě nejsou protichůdné instrukce,
duplicity nebo zastaralé vzory které by zbytečně mátly find_repeat_action.

5 typů kontroly:
  D1: Duplicity — stejný (from_addr + subject_normalized) má víc záznamů
  D2: Protichůdné akce — stejný sender má spam + jinou akci
  D3: Stale records — záznamy starší než 180 dní
  D4: Whitelist konflikt — kontakt v apple_contacts má spam záznam
  D5: Sirotci — single-occurrence + human_corrected=False (jen Llama, ne Pavel)

Read-only — žádné delete. Cleanup je separátní skript po schválení.
"""

import os
import re
import json
import httpx
from collections import defaultdict, Counter
from datetime import datetime, timezone, timedelta

# Konfigurace
CHROMA_HOST = os.getenv("CHROMA_HOST", "chromadb")
CHROMA_PORT = os.getenv("CHROMA_PORT", "8000")
COLLECTION_NAME = "email_actions"
STALE_DAYS = 180


def _api_base() -> str:
    return f"http://{CHROMA_HOST}:{CHROMA_PORT}/api/v2"


def _find_collection() -> str:
    """Vrátí ID collection email_actions."""
    base = _api_base()
    r = httpx.get(f"{base}/tenants/default_tenant/databases/default_database/collections", timeout=10)
    r.raise_for_status()
    cols = r.json()
    for c in cols:
        if c["name"] == COLLECTION_NAME:
            return c["id"]
    raise SystemExit(f"Collection {COLLECTION_NAME} nenalezena")


def _fetch_all(coll_id: str) -> dict:
    """Stáhne všechny záznamy (bez embeddings — kvůli velikosti)."""
    base = _api_base()
    url = f"{base}/tenants/default_tenant/databases/default_database/collections/{coll_id}/get"
    r = httpx.post(url, json={"include": ["metadatas", "documents"]}, timeout=30)
    r.raise_for_status()
    return r.json()


def _normalize_subject(s: str) -> str:
    """Odstranit Re:/Fwd: prefix + lowercase + collapse whitespace."""
    if not s:
        return ""
    s = re.sub(r"^(Re|Fwd?|RE|FWD?):\s*", "", s.strip(), flags=re.IGNORECASE).strip()
    return re.sub(r"\s+", " ", s.lower())


def _extract_email(addr: str) -> str:
    """Extrahuje plain email z 'Name <email@x.com>'."""
    if not addr:
        return ""
    m = re.search(r"<([^>]+@[^>]+)>", addr)
    if m:
        return m.group(1).strip().lower()
    m = re.search(r"(\S+@\S+\.\S+)", addr)
    return m.group(1).strip().lower() if m else addr.lower()


def _fetch_contact_emails() -> set[str]:
    """Vrátí množinu všech emailových adres z apple_contacts (lower)."""
    try:
        # ingest_apple_apps používá psycopg2 přes db.get_conn
        from db import get_conn
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT DISTINCT lower(e->>'value') AS email
            FROM apple_contacts, jsonb_array_elements(emails) AS e
            WHERE e->>'value' IS NOT NULL
        """)
        emails = {row[0] for row in cur.fetchall() if row[0]}
        cur.close()
        conn.close()
        return emails
    except Exception as e:
        print(f"  ⚠️ apple_contacts fetch failed: {e}")
        return set()


def main():
    print("=" * 70)
    print("ChromaDB email_actions — AUDIT")
    print("=" * 70)

    coll_id = _find_collection()
    data = _fetch_all(coll_id)
    ids = data.get("ids", [])
    metas = data.get("metadatas", [])
    docs = data.get("documents", [])

    total = len(ids)
    print(f"\nCelkem záznamů: {total}")

    # Group by sender pro analýzy
    by_sender = defaultdict(list)
    by_dedup_key = defaultdict(list)
    now = datetime.now(timezone.utc)
    stale_cutoff = now - timedelta(days=STALE_DAYS)

    parsed = []
    for i, m in enumerate(metas):
        sender = _extract_email(m.get("from_addr", ""))
        subj_norm = _normalize_subject(m.get("subject", ""))
        ts_raw = m.get("timestamp")
        try:
            ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00")) if ts_raw else None
        except Exception:
            ts = None
        item = {
            "id": ids[i],
            "sender": sender,
            "from_addr": m.get("from_addr", ""),
            "subject": m.get("subject", ""),
            "subj_norm": subj_norm,
            "action": m.get("action", ""),
            "typ": m.get("typ", ""),
            "human_corrected": m.get("human_corrected", False),
            "timestamp": ts,
            "ts_raw": ts_raw,
        }
        parsed.append(item)
        by_sender[sender].append(item)
        by_dedup_key[(sender, subj_norm)].append(item)

    # ── D1: Duplicity (stejný sender + subject_normalized) ──────────────────
    print("\n" + "─" * 70)
    print("D1: DUPLICITY (stejný sender + normalizovaný subject)")
    print("─" * 70)
    dups = {k: v for k, v in by_dedup_key.items() if len(v) > 1}
    print(f"Skupin s duplikáty: {len(dups)}")
    print(f"Celkem duplicitních záznamů: {sum(len(v) for v in dups.values())}")
    print(f"Záznamů ke smazání (ponechat 1 nejnovější s human_corrected=True): {sum(len(v)-1 for v in dups.values())}")
    if dups:
        print("\nTop 5 nejvíce duplicit:")
        for (sender, subj), items in sorted(dups.items(), key=lambda x: -len(x[1]))[:5]:
            actions = [i["action"] for i in items]
            print(f"  {len(items)}× | {sender[:40]:<40} | {subj[:50]} | actions: {actions}")

    # ── D2: Protichůdné akce (stejný sender, různé akce) ───────────────────
    print("\n" + "─" * 70)
    print("D2: PROTICHŮDNÉ AKCE (stejný sender má víc různých akcí)")
    print("─" * 70)
    conflicts = {}
    for sender, items in by_sender.items():
        if not sender or len(items) < 2:
            continue
        actions = Counter(i["action"] for i in items if i["action"])
        # Konflikt = víc různých akcí (ne jen různý počet stejné)
        if len(actions) > 1:
            conflicts[sender] = (actions, items)
    print(f"Senders s konfliktními akcemi: {len(conflicts)}")
    if conflicts:
        print("\nKonflikty:")
        for sender, (actions, items) in sorted(conflicts.items(), key=lambda x: -sum(x[1][0].values()))[:10]:
            print(f"  {sender[:50]:<50} | {dict(actions)}")
            # Vypsat detail per záznam (subject + action + datum + Pavel/AI)
            for it in items[:5]:
                src = "👤" if it["human_corrected"] else "🤖"
                ts = it["timestamp"].strftime("%m-%d") if it["timestamp"] else "??"
                print(f"      {src} {it['action']:<8} {ts}  {it['subject'][:60]}")

    # ── D3: Stale records (starší 180 dní) ──────────────────────────────────
    print("\n" + "─" * 70)
    print(f"D3: STALE RECORDS (starší {STALE_DAYS} dní)")
    print("─" * 70)
    stale = [i for i in parsed if i["timestamp"] and i["timestamp"] < stale_cutoff]
    print(f"Záznamů starších {STALE_DAYS} dní: {len(stale)}")
    if stale:
        oldest = min(stale, key=lambda x: x["timestamp"])
        print(f"Nejstarší: {oldest['timestamp'].date()} — {oldest['from_addr'][:40]} | {oldest['subject'][:50]}")

    # ── D4: Whitelist konflikt (kontakt v apple_contacts má spam) ──────────
    print("\n" + "─" * 70)
    print("D4: WHITELIST KONFLIKT (sender v apple_contacts MÁ spam akci)")
    print("─" * 70)
    contacts = _fetch_contact_emails()
    print(f"Kontaktů v apple_contacts: {len(contacts)}")
    whitelist_conflicts = [
        i for i in parsed
        if i["action"] == "spam" and i["sender"] in contacts
    ]
    print(f"Záznamů 'spam' u kontaktů: {len(whitelist_conflicts)}")
    if whitelist_conflicts:
        print("\nKonflikty (sender je kontakt ale má spam vzor):")
        for i in whitelist_conflicts[:10]:
            ts = i["timestamp"].strftime("%m-%d") if i["timestamp"] else "??"
            src = "👤" if i["human_corrected"] else "🤖"
            print(f"  {src} {ts}  {i['from_addr'][:50]:<50} | {i['subject'][:60]}")

    # ── D5: Sirotci (single + ne human_corrected) ──────────────────────────
    print("\n" + "─" * 70)
    print("D5: SIROTCI (single-occurrence sender + Llama-only, ne Pavel)")
    print("─" * 70)
    orphans = []
    for sender, items in by_sender.items():
        if len(items) == 1 and not items[0]["human_corrected"]:
            orphans.append(items[0])
    print(f"Sirotčích záznamů: {len(orphans)}")
    if orphans:
        actions_count = Counter(o["action"] for o in orphans)
        print(f"Distribuce akcí: {dict(actions_count)}")

    # ── Souhrn ─────────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("SOUHRN")
    print("=" * 70)
    n_dup_to_remove = sum(len(v) - 1 for v in dups.values())
    print(f"Total:                                    {total}")
    print(f"D1 duplicity (ke smazání):                {n_dup_to_remove}")
    print(f"D2 senders s konflikty:                   {len(conflicts)}")
    print(f"D3 stale (>180 dní):                      {len(stale)}")
    print(f"D4 whitelist konflikt:                    {len(whitelist_conflicts)}")
    print(f"D5 sirotci (Llama-only, single):          {len(orphans)}")

    print("\nAkce: žádný delete neproveden (read-only audit).")


if __name__ == "__main__":
    main()

"""
ChromaDB email_actions — DEDUPLIKACE (D1 z chroma_audit.py).

Cíl: smazat duplicitní záznamy se stejným (sender + subject_normalized).
Z každé duplicitní skupiny ponechat:
  1. Nejnovější s human_corrected=True (Pavel rozhodl), nebo pokud žádný
  2. Nejnovější (Llama-classified)

Spuštění:
  --dry-run     vypíše které ID se smaže (default — bezpečné)
  --apply       reálně smaže (potřebuje exact flag)
"""

import os
import re
import sys
import httpx
from collections import defaultdict
from datetime import datetime

CHROMA_HOST = os.getenv("CHROMA_HOST", "chromadb")
CHROMA_PORT = os.getenv("CHROMA_PORT", "8000")
COLLECTION_NAME = "email_actions"


def _api_base() -> str:
    return f"http://{CHROMA_HOST}:{CHROMA_PORT}/api/v2"


def _find_collection() -> str:
    base = _api_base()
    r = httpx.get(f"{base}/tenants/default_tenant/databases/default_database/collections", timeout=10)
    r.raise_for_status()
    for c in r.json():
        if c["name"] == COLLECTION_NAME:
            return c["id"]
    raise SystemExit(f"Collection {COLLECTION_NAME} nenalezena")


def _fetch_all(coll_id: str) -> dict:
    base = _api_base()
    url = f"{base}/tenants/default_tenant/databases/default_database/collections/{coll_id}/get"
    r = httpx.post(url, json={"include": ["metadatas"]}, timeout=30)
    r.raise_for_status()
    return r.json()


def _normalize_subject(s: str) -> str:
    if not s:
        return ""
    s = re.sub(r"^(Re|Fwd?|RE|FWD?):\s*", "", s.strip(), flags=re.IGNORECASE).strip()
    return re.sub(r"\s+", " ", s.lower())


def _extract_email(addr: str) -> str:
    if not addr:
        return ""
    m = re.search(r"<([^>]+@[^>]+)>", addr)
    if m:
        return m.group(1).strip().lower()
    m = re.search(r"(\S+@\S+\.\S+)", addr)
    return m.group(1).strip().lower() if m else addr.lower()


def _delete(coll_id: str, ids: list[str]) -> int:
    base = _api_base()
    url = f"{base}/tenants/default_tenant/databases/default_database/collections/{coll_id}/delete"
    r = httpx.post(url, json={"ids": ids}, timeout=30)
    r.raise_for_status()
    return len(ids)


def main():
    apply_mode = "--apply" in sys.argv
    dry_run = not apply_mode

    print("=" * 70)
    print(f"ChromaDB email_actions — DEDUP ({'DRY-RUN' if dry_run else '⚠️  APPLY MODE'})")
    print("=" * 70)

    coll_id = _find_collection()
    data = _fetch_all(coll_id)
    ids = data.get("ids", [])
    metas = data.get("metadatas", [])
    print(f"\nCelkem záznamů: {len(ids)}")

    # Group by (sender, subject_normalized)
    groups = defaultdict(list)
    for i, m in enumerate(metas):
        sender = _extract_email(m.get("from_addr", ""))
        subj_norm = _normalize_subject(m.get("subject", ""))
        ts_raw = m.get("timestamp")
        try:
            ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00")) if ts_raw else None
        except Exception:
            ts = None
        groups[(sender, subj_norm)].append({
            "id": ids[i],
            "from_addr": m.get("from_addr", ""),
            "subject": m.get("subject", ""),
            "action": m.get("action", ""),
            "human_corrected": m.get("human_corrected", False),
            "timestamp": ts,
        })

    duplicate_groups = [v for v in groups.values() if len(v) > 1]
    print(f"Duplicitních skupin: {len(duplicate_groups)}")

    to_keep = []
    to_delete = []

    for group in duplicate_groups:
        # Sort: human_corrected desc, then timestamp desc
        group.sort(key=lambda x: (
            1 if x["human_corrected"] else 0,
            x["timestamp"] or datetime.min.replace(tzinfo=None),
        ), reverse=True)
        keep = group[0]
        delete = group[1:]
        to_keep.append(keep)
        to_delete.extend(delete)

    print(f"Záznamů ponecháno: {len(to_keep)}")
    print(f"Záznamů ke smazání: {len(to_delete)}")

    if to_delete:
        print(f"\n{'─'*70}")
        print("DETAILY (per skupina ke smazání):")
        print(f"{'─'*70}")
        for group in duplicate_groups:
            sender = _extract_email(group[0]["from_addr"])
            subj = group[0]["subject"][:55]
            print(f"\n  📦 {sender[:40]}  | {subj}")
            for it in group:
                src = "👤" if it["human_corrected"] else "🤖"
                ts = it["timestamp"].strftime("%m-%d %H:%M") if it["timestamp"] else "??"
                marker = "✅ KEEP" if it["id"] == group[0]["id"] else "🗑  DELETE"
                print(f"    {marker}  {src} {ts}  action={it['action']:<8}  id={it['id'][:20]}...")

    print(f"\n{'='*70}")
    if dry_run:
        print(f"DRY-RUN: žádné smazání. Pro reálné smazání spusť s --apply.")
        print(f"Smazalo by se: {len(to_delete)} záznamů, zůstalo by: {len(ids) - len(to_delete)}")
    else:
        if to_delete:
            ids_to_delete = [it["id"] for it in to_delete]
            n = _delete(coll_id, ids_to_delete)
            print(f"✅ Smazáno {n} záznamů.")
            print(f"Zbývá: {len(ids) - n} záznamů.")
        else:
            print("Nic ke smazání.")
    print("=" * 70)


if __name__ == "__main__":
    main()

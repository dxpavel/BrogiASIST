#!/usr/bin/env python3
"""check_mail_indexed.py — projde emaily v DB a aktualizuje flag mail_indexed
   podle stavu v Apple Mail (přes mail-bridge daemon).

Použití:
  python3 check_mail_indexed.py                  # default: kde checked_at je NULL nebo > {SCAN_RECHECK_HOURS}h staré
  python3 check_mail_indexed.py --all            # všechny emaily, ignoruj cache
  python3 check_mail_indexed.py --limit 50       # jen prvních N
  python3 check_mail_indexed.py --recheck-hours 12  # přepiš ENV SCAN_RECHECK_HOURS
  python3 check_mail_indexed.py --bridge URL     # custom mail-bridge (default localhost:9102)
  python3 check_mail_indexed.py --pg-host HOST   # custom postgres host (default localhost)
  python3 check_mail_indexed.py --pg-port PORT   # custom postgres port (default 5433 = DEV)

ENV proměnné:
  SCAN_RECHECK_HOURS  — kolik hodin staré flagy se znovu kontrolují (default 24)
  MAIL_BRIDGE_URL     — URL daemona (default http://localhost:9102)
  POSTGRES_HOST       — default localhost
  POSTGRES_PORT       — default 5433 (DEV)
  POSTGRES_DB         — default assistance
  POSTGRES_USER       — default brogi
  POSTGRES_PASSWORD   — default brogi_dev_2026

DB: brogi/brogi_dev_2026 @ localhost:5433/assistance (DEV).
Pro PROD: POSTGRES_PORT=5432.
"""
import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.error

import psycopg2


def parse_args():
    p = argparse.ArgumentParser(description="Aktualizace mail_indexed flagu z Apple Mail")
    p.add_argument("--all", action="store_true",
                   help="zkontroluj všechny emaily (ignoruj recheck-hours cache)")
    p.add_argument("--limit", type=int, default=None,
                   help="jen prvních N emailů")
    p.add_argument("--recheck-hours", type=int,
                   default=int(os.getenv("SCAN_RECHECK_HOURS", "24")),
                   help="po kolika hodinách znovu kontrolovat (default ENV SCAN_RECHECK_HOURS nebo 24)")
    p.add_argument("--bridge",
                   default=os.getenv("MAIL_BRIDGE_URL", "http://localhost:9102"),
                   help="mail-bridge URL (default ENV MAIL_BRIDGE_URL nebo http://localhost:9102)")
    p.add_argument("--pg-host", default=os.getenv("POSTGRES_HOST", "localhost"))
    p.add_argument("--pg-port", type=int, default=int(os.getenv("POSTGRES_PORT", "5433")))
    p.add_argument("--pg-db", default=os.getenv("POSTGRES_DB", "assistance"))
    p.add_argument("--pg-user", default=os.getenv("POSTGRES_USER", "brogi"))
    p.add_argument("--pg-pass", default=os.getenv("POSTGRES_PASSWORD", "brogi_dev_2026"))
    p.add_argument("--dry-run", action="store_true",
                   help="jen vypiš co by se aktualizovalo, neuloží")
    return p.parse_args()


def check_bridge_health(bridge_url: str) -> bool:
    try:
        with urllib.request.urlopen(f"{bridge_url}/health", timeout=3) as r:
            return r.status == 200
    except Exception as e:
        print(f"[ERROR] mail-bridge unreachable at {bridge_url}: {e}")
        return False


def check_message(bridge_url: str, message_id: str, timeout_s: int = 8):
    """Vrátí True (indexed), False (not indexed), None (error/skip)."""
    payload = json.dumps({"message_id": message_id, "timeout_s": timeout_s}).encode()
    req = urllib.request.Request(
        f"{bridge_url}/check",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout_s + 5) as r:
            data = json.loads(r.read())
            return bool(data.get("indexed", False))
    except urllib.error.HTTPError as e:
        if e.code == 400:
            print(f"  [SKIP] invalid message_id (400)")
            return None
        print(f"  [ERROR] HTTP {e.code}: {e.reason}")
        return None
    except Exception as e:
        print(f"  [ERROR] {e}")
        return None


def main():
    args = parse_args()

    if not check_bridge_health(args.bridge):
        sys.exit(1)
    print(f"[OK] mail-bridge alive at {args.bridge} | recheck-hours={args.recheck_hours}")

    conn = psycopg2.connect(
        host=args.pg_host, port=args.pg_port, dbname=args.pg_db,
        user=args.pg_user, password=args.pg_pass,
    )
    conn.autocommit = False
    cur = conn.cursor()

    where_recheck = "" if args.all else \
        f"AND (mail_indexed_checked_at IS NULL OR mail_indexed_checked_at < now() - interval '{args.recheck_hours} hours')"
    limit_clause = f"LIMIT {args.limit}" if args.limit else ""

    cur.execute(f"""
        SELECT id, source_id, subject
        FROM email_messages
        WHERE source_id IS NOT NULL
          AND source_id LIKE '<%@%>'
          {where_recheck}
        ORDER BY sent_at DESC NULLS LAST
        {limit_clause}
    """)
    rows = cur.fetchall()
    print(f"[INFO] ke kontrole: {len(rows)} emailů")
    if not rows:
        print("[OK] nic ke zpracování")
        return

    stats = {"indexed_true": 0, "indexed_false": 0, "skip": 0, "changed": 0}
    t0 = time.time()

    for i, (eid, src, subj) in enumerate(rows, 1):
        subj_short = (subj or "")[:60]
        result = check_message(args.bridge, src)
        if result is None:
            stats["skip"] += 1
            print(f"[{i}/{len(rows)}] SKIP {src} ({subj_short})")
            continue

        if result:
            stats["indexed_true"] += 1
        else:
            stats["indexed_false"] += 1

        if args.dry_run:
            print(f"[{i}/{len(rows)}] DRY: {src} -> indexed={result} ({subj_short})")
            continue

        cur.execute("""
            UPDATE email_messages
               SET mail_indexed = %s,
                   mail_indexed_checked_at = now()
             WHERE id = %s
               AND (mail_indexed IS DISTINCT FROM %s OR mail_indexed_checked_at IS NULL)
            RETURNING id
        """, (result, eid, result))
        if cur.fetchone():
            stats["changed"] += 1
        # touch checked_at i pokud se hodnota nezměnila
        cur.execute("""
            UPDATE email_messages
               SET mail_indexed_checked_at = now()
             WHERE id = %s
        """, (eid,))
        conn.commit()
        print(f"[{i}/{len(rows)}] {'✓' if result else '✗'} {src} ({subj_short})")

    cur.close()
    conn.close()
    dur = time.time() - t0
    print()
    print(f"[DONE] {dur:.1f}s | indexed=TRUE: {stats['indexed_true']} | "
          f"indexed=FALSE: {stats['indexed_false']} | skip: {stats['skip']} | "
          f"changed: {stats['changed']}")


if __name__ == "__main__":
    main()

"""
MantisBT ingest — issues ze všech projektů, aktualizované za posledních 7 dní.
"""

import os
import json
import urllib.request
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from db import get_conn

load_dotenv(os.path.join(os.path.dirname(__file__), "../../.env"))

MANTIS_URL   = os.getenv("MANTIS_URL", "https://servicedesk.dxpavel.cz")
MANTIS_TOKEN = os.getenv("MANTIS_API_TOKEN", "")
API_BASE     = f"{MANTIS_URL}/api/rest"
DAYS_BACK    = 7
PAGE_SIZE    = 50


def api_get(path: str) -> dict:
    req = urllib.request.Request(
        f"{API_BASE}/{path}",
        headers={"Authorization": MANTIS_TOKEN, "User-Agent": "BrogiASIST/1.0"},
    )
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def fetch_issues(project_id: int, since: datetime = None) -> list:
    issues = []
    page = 1
    while True:
        data = api_get(f"issues?project_id={project_id}&page_size={PAGE_SIZE}&page={page}")
        batch = data.get("issues", [])
        if not batch:
            break
        for issue in batch:
            if since:
                updated_raw = issue.get("updated_at", "")
                if updated_raw:
                    updated_dt = datetime.fromisoformat(updated_raw.replace("Z", "+00:00"))
                    if updated_dt < since:
                        return issues
            issues.append(issue)
        if len(batch) < PAGE_SIZE:
            break
        page += 1
    return issues


def upsert_issues(issues: list) -> tuple[int, int]:
    conn = get_conn()
    cur = conn.cursor()
    new_count = 0
    skip_count = 0

    for issue in issues:
        source_id   = str(issue.get("id", ""))
        project     = issue.get("project", {})
        reporter    = issue.get("reporter", {}).get("display_name", "")
        assigned    = issue.get("handler", {}).get("display_name", "") if issue.get("handler") else ""
        istatus     = issue.get("status", {}).get("name", "")
        priority    = issue.get("priority", {}).get("name", "")
        severity    = issue.get("severity", {}).get("name", "")

        def parse_dt(val):
            if not val:
                return None
            return datetime.fromisoformat(val.replace("Z", "+00:00"))

        cur.execute("""
            INSERT INTO mantis_issues
                (source_type, source_id, raw_payload, project_id, project_name,
                 summary, description, issue_status, priority, severity,
                 reporter, assigned_to, created_at, updated_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (source_id) DO UPDATE SET
                raw_payload  = EXCLUDED.raw_payload,
                issue_status = EXCLUDED.issue_status,
                assigned_to  = EXCLUDED.assigned_to,
                updated_at   = EXCLUDED.updated_at,
                ingested_at  = NOW()
        """, (
            "mantis", source_id, json.dumps(issue),
            project.get("id"), project.get("name"),
            issue.get("summary", ""),
            issue.get("description", ""),
            istatus, priority, severity,
            reporter, assigned,
            parse_dt(issue.get("created_at")),
            parse_dt(issue.get("updated_at")),
        ))
        if cur.rowcount:
            new_count += 1
        else:
            skip_count += 1

    conn.commit()
    conn.close()
    return new_count, skip_count


PROJECT_IDS = [5, 16, 17]  # DXP_SOLUTIONS, DXP_SERVICEDESK, DXP_PHOTOSPACE

if __name__ == "__main__":
    import sys
    full = "--full" in sys.argv
    since = None if full else datetime.now(tz=timezone.utc) - timedelta(days=DAYS_BACK)
    label = "vše" if full else f"od {since.strftime('%Y-%m-%d')}"
    print(f"MantisBT ingest — {label}")
    total_new = 0
    for pid in PROJECT_IDS:
        try:
            issues = fetch_issues(pid, since)
            new_c, skip_c = upsert_issues(issues)
            print(f"  projekt {pid}: {len(issues)} issues → nových/aktualizovaných: {new_c}, beze změny: {skip_c}")
            total_new += new_c
        except Exception as e:
            print(f"  projekt {pid}: CHYBA: {e}")
    print(f"Celkem: {total_new}")

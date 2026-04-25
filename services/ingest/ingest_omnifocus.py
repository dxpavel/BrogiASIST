import os
import httpx
import logging
from db import get_conn

logger = logging.getLogger(__name__)

BRIDGE_URL = os.getenv("APPLE_BRIDGE_URL", "http://host.docker.internal:9100")


def ingest_omnifocus():
    try:
        r = httpx.get(f"{BRIDGE_URL}/omnifocus/tasks", timeout=120)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        logger.error(f"OmniFocus bridge nedostupný: {e}")
        return

    tasks = data.get("tasks", [])
    if not tasks:
        logger.info("OmniFocus: žádné tasky")
        return

    conn = get_conn()
    cur = conn.cursor()
    upserted = 0
    for t in tasks:
        try:
            cur.execute("""
                INSERT INTO omnifocus_tasks
                    (source_id, name, project, status, flagged, due_at, defer_at,
                     completed_at, modified_at, tags, note, in_inbox, raw_payload)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s::jsonb)
                ON CONFLICT (source_id) DO UPDATE SET
                    name        = EXCLUDED.name,
                    project     = EXCLUDED.project,
                    status      = EXCLUDED.status,
                    flagged     = EXCLUDED.flagged,
                    due_at      = EXCLUDED.due_at,
                    defer_at    = EXCLUDED.defer_at,
                    completed_at= EXCLUDED.completed_at,
                    modified_at = EXCLUDED.modified_at,
                    tags        = EXCLUDED.tags,
                    note        = EXCLUDED.note,
                    in_inbox    = EXCLUDED.in_inbox,
                    raw_payload = EXCLUDED.raw_payload,
                    ingested_at = NOW()
            """, (
                t["id"], t["name"], t.get("project"), t.get("status"),
                t.get("flagged", False),
                t.get("due_at"), t.get("defer_at"),
                t.get("completed_at"), t.get("modified_at"),
                __import__("json").dumps(t.get("tags", [])),
                t.get("note"), t.get("in_inbox", False),
                __import__("json").dumps(t)
            ))
            upserted += 1
        except Exception as e:
            logger.warning(f"OmniFocus upsert error ({t.get('id')}): {e}")
            conn.rollback()
            continue
    conn.commit()
    cur.close()
    conn.close()
    logger.info(f"OmniFocus: upserted {upserted}/{len(tasks)} tasků")

import os
import json
import httpx
import logging
from db import get_conn

logger = logging.getLogger(__name__)

BRIDGE_URL = os.getenv("APPLE_BRIDGE_URL", "http://host.docker.internal:9100")


def _bridge_get(path: str, timeout: int = 60) -> dict | None:
    try:
        r = httpx.get(f"{BRIDGE_URL}{path}", timeout=timeout)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.error(f"Bridge {path}: {e}")
        return None


def ingest_notes():
    data = _bridge_get("/notes/all", timeout=60)
    if not data or not data.get("ok"):
        return
    items = data.get("notes", [])
    conn = get_conn()
    cur = conn.cursor()
    upserted = 0
    for n in items:
        try:
            cur.execute("""
                INSERT INTO apple_notes (source_id, name, body, modified_at, created_at)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (source_id) DO UPDATE SET
                    name=EXCLUDED.name, body=EXCLUDED.body,
                    modified_at=EXCLUDED.modified_at, ingested_at=NOW()
                WHERE apple_notes.modified_at IS DISTINCT FROM EXCLUDED.modified_at
            """, (n["id"], n.get("name"), n.get("body"), n.get("modified_at"), n.get("created_at")))
            upserted += 1
        except Exception as e:
            logger.warning(f"Notes upsert {n.get('id')}: {e}")
            conn.rollback()
    conn.commit()
    cur.close()
    conn.close()
    logger.info(f"Notes: upserted {upserted}/{len(items)}")


def ingest_reminders():
    data = _bridge_get("/reminders/all", timeout=30)
    if not data or not data.get("ok"):
        return
    items = data.get("reminders", [])
    conn = get_conn()
    cur = conn.cursor()
    upserted = 0
    for r in items:
        try:
            cur.execute("""
                INSERT INTO apple_reminders
                    (source_id, name, list_name, body, flagged, completed, due_at, remind_at, modified_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (source_id) DO UPDATE SET
                    name=EXCLUDED.name, list_name=EXCLUDED.list_name,
                    body=EXCLUDED.body, flagged=EXCLUDED.flagged,
                    completed=EXCLUDED.completed, due_at=EXCLUDED.due_at,
                    remind_at=EXCLUDED.remind_at, modified_at=EXCLUDED.modified_at,
                    ingested_at=NOW()
            """, (r["id"], r["name"], r.get("list"), r.get("body"),
                  r.get("flagged", False), r.get("completed", False),
                  r.get("due_at"), r.get("remind_at"), r.get("modified_at")))
            upserted += 1
        except Exception as e:
            logger.warning(f"Reminders upsert {r.get('id')}: {e}")
            conn.rollback()
    conn.commit()
    cur.close()
    conn.close()
    logger.info(f"Reminders: upserted {upserted}/{len(items)}")


def ingest_contacts():
    data = _bridge_get("/contacts/all", timeout=60)
    if not data or not data.get("ok"):
        return
    items = data.get("contacts", [])
    conn = get_conn()
    cur = conn.cursor()
    upserted = 0
    for c in items:
        try:
            cur.execute("""
                INSERT INTO apple_contacts
                    (source_id, first_name, last_name, organization, emails, phones, groups, modified_at)
                VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s)
                ON CONFLICT (source_id) DO UPDATE SET
                    first_name=EXCLUDED.first_name, last_name=EXCLUDED.last_name,
                    organization=EXCLUDED.organization, emails=EXCLUDED.emails,
                    phones=EXCLUDED.phones, groups=EXCLUDED.groups,
                    modified_at=EXCLUDED.modified_at,
                    ingested_at=NOW()
            """, (c["id"], c.get("first"), c.get("last"), c.get("org"),
                  json.dumps(c.get("emails", [])), json.dumps(c.get("phones", [])),
                  json.dumps(c.get("groups", [])),
                  c.get("modified_at")))
            upserted += 1
        except Exception as e:
            logger.warning(f"Contacts upsert {c.get('id')}: {e}")
            conn.rollback()
    conn.commit()
    cur.close()
    conn.close()
    logger.info(f"Contacts: upserted {upserted}/{len(items)}")


def ingest_calendar():
    data = _bridge_get("/calendar/events?days=60", timeout=60)
    if not data or not data.get("ok"):
        logger.warning(f"Calendar: {data.get('error') if data else 'bridge error'}")
        return
    items = data.get("events", [])
    conn = get_conn()
    cur = conn.cursor()
    upserted = 0
    for e in items:
        try:
            cur.execute("""
                INSERT INTO calendar_events
                    (source_id, summary, calendar, start_at, end_at, all_day, location)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (source_id) DO UPDATE SET
                    summary=EXCLUDED.summary, calendar=EXCLUDED.calendar,
                    start_at=EXCLUDED.start_at, end_at=EXCLUDED.end_at,
                    all_day=EXCLUDED.all_day, location=EXCLUDED.location,
                    ingested_at=NOW()
            """, (e["id"], e.get("summary"), e.get("calendar"),
                  e.get("start_at"), e.get("end_at"),
                  e.get("all_day", False), e.get("location")))
            upserted += 1
        except Exception as e2:
            logger.warning(f"Calendar upsert: {e2}")
            conn.rollback()
    conn.commit()
    cur.close()
    conn.close()
    logger.info(f"Calendar: upserted {upserted}/{len(items)}")

import os
import json
import hashlib
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
    """Ingest Apple Contacts s hash-check optimalizací.

    JXA cesta vrací prázdné emails/phones (viz Bridge endpoint), takže
    UPDATE musí ZACHOVAT existující emails/phones — jinak by jeden běh
    smazal všechna historická data. Aktualizujeme reálně jen
    name/org/groups/modified_at.

    Hash check: spočítá sha256 z odpovědi. Pokud == minulý hash uložený
    v config tabulce → skip ingest (žádné DB writes). Tím interval 12h
    znamená nuluvý DB load pokud Pavel nezměnil kontakty.
    """
    data = _bridge_get("/contacts/all", timeout=300)
    if not data or not data.get("ok"):
        logger.warning(f"Contacts fetch nepovedlo se: ok={data and data.get('ok')} err={data and data.get('error')}")
        return
    items = data.get("contacts", [])
    if not items:
        logger.info("Contacts: prázdná odpověď, skip")
        return

    # Hash z aktuální response (sort_keys pro deterministic hash)
    payload = json.dumps(items, sort_keys=True, ensure_ascii=False).encode("utf-8")
    h = hashlib.sha256(payload).hexdigest()

    conn = get_conn()
    cur = conn.cursor()

    # Last hash z config — pokud stejný, nic se nezměnilo
    cur.execute("SELECT value FROM config WHERE key = 'apple_contacts_last_hash'")
    row = cur.fetchone()
    last_hash = row[0] if row else None
    if last_hash == h:
        logger.info(f"Contacts: žádné změny od posledního ingestu (hash {h[:12]}…) — skip")
        cur.close()
        conn.close()
        return

    upserted = 0
    for c in items:
        try:
            # CASE WHEN zajistí, že prázdné emails/phones (JXA vrací []) nepřepíší
            # existující data v DB. Refresh emails/phones řešen separátně přes
            # legacy /contacts/all_sqlite (až bude FDA fungovat).
            cur.execute("""
                INSERT INTO apple_contacts
                    (source_id, first_name, last_name, organization, emails, phones, groups, modified_at)
                VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s)
                ON CONFLICT (source_id) DO UPDATE SET
                    first_name=EXCLUDED.first_name,
                    last_name=EXCLUDED.last_name,
                    organization=EXCLUDED.organization,
                    emails=CASE WHEN jsonb_array_length(EXCLUDED.emails) > 0
                                THEN EXCLUDED.emails
                                ELSE apple_contacts.emails END,
                    phones=CASE WHEN jsonb_array_length(EXCLUDED.phones) > 0
                                THEN EXCLUDED.phones
                                ELSE apple_contacts.phones END,
                    groups=EXCLUDED.groups,
                    modified_at=COALESCE(EXCLUDED.modified_at, apple_contacts.modified_at),
                    ingested_at=NOW()
            """, (c["id"], c.get("first"), c.get("last"), c.get("org"),
                  json.dumps(c.get("emails", [])), json.dumps(c.get("phones", [])),
                  json.dumps(c.get("groups", [])),
                  c.get("modified_at")))
            upserted += 1
        except Exception as e:
            logger.warning(f"Contacts upsert {c.get('id')}: {e}")
            conn.rollback()

    # Uložit nový hash
    cur.execute("""
        INSERT INTO config (key, value, module) VALUES ('apple_contacts_last_hash', %s, 'apple_apps')
        ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, updated_at=NOW()
    """, (h,))

    conn.commit()
    cur.close()
    conn.close()
    logger.info(f"Contacts: upserted {upserted}/{len(items)} (změny detekovány, nový hash {h[:12]}…)")


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

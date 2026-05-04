import os
import httpx
import psycopg2
from datetime import datetime
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "../../.env"))

app = FastAPI(title="BrogiASIST Dashboard")
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")

DB_CONFIG = {
    "host": os.getenv("POSTGRES_HOST", "localhost"),
    "port": int(os.getenv("POSTGRES_PORT", "5433")),
    "dbname": os.getenv("POSTGRES_DB", "assistance"),
    "user": os.getenv("POSTGRES_USER", "brogi"),
    "password": os.getenv("POSTGRES_PASSWORD", ""),
    "connect_timeout": 3,
}
CHROMA_HOST = os.getenv("CHROMA_HOST", "localhost")
CHROMA_PORT = os.getenv("CHROMA_PORT", "8000")
INGEST_URL = os.getenv("INGEST_URL", "http://brogi_scheduler:9001")


def get_db_status() -> dict:
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()

        tables = ["email_messages", "rss_articles", "youtube_videos", "mantis_issues", "omnifocus_tasks", "apple_contacts", "actions", "sessions", "config", "attachments"]
        counts = {}
        for t in tables:
            cur.execute(f"SELECT COUNT(*) FROM {t}")
            counts[t] = cur.fetchone()[0]

        cur.execute("""
            SELECT source_type, action_type, status, created_at
            FROM actions
            ORDER BY created_at DESC
            LIMIT 10
        """)
        recent_actions = [
            {"source_type": r[0], "action_type": r[1], "status": r[2], "created_at": r[3]}
            for r in cur.fetchall()
        ]

        cur.execute("""
            SELECT mailbox, COUNT(*), MAX(ingested_at)
            FROM email_messages
            GROUP BY mailbox
            ORDER BY COUNT(*) DESC
        """)
        email_stats = [
            {"mailbox": r[0], "count": r[1], "last_ingest": r[2]}
            for r in cur.fetchall()
        ]

        cur.execute("""
            SELECT feed_title, COUNT(*), MAX(ingested_at)
            FROM rss_articles
            GROUP BY feed_title
            ORDER BY COUNT(*) DESC
            LIMIT 20
        """)
        rss_stats = [
            {"feed": r[0], "count": r[1], "last_ingest": r[2]}
            for r in cur.fetchall()
        ]

        cur.execute("""
            SELECT id, mailbox, from_address, subject, sent_at, firma, typ, task_status, is_spam, ai_confidence, human_reviewed, source_id, mail_indexed, status
            FROM email_messages
            WHERE is_spam = FALSE
            ORDER BY sent_at DESC NULLS LAST
            LIMIT 100
        """)
        def extract_name(addr):
            if not addr:
                return "—"
            if "<" in addr:
                name = addr.split("<")[0].strip().strip('"')
                return name if name else addr.split("<")[1].rstrip(">")
            return addr.split("@")[0] if "@" in addr else addr

        def short_mailbox(m):
            return m.split("@")[0] if m else "?"

        email_log = [
            {"id": str(r[0]), "mailbox": r[1] or "?", "from_name": extract_name(r[2]),
             "from_address": r[2] or "—",
             "subject": r[3] or "(bez předmětu)", "sent_at": r[4],
             "firma": r[5], "typ": r[6], "task_status": r[7], "is_spam": r[8],
             "confidence": r[9], "human_reviewed": r[10], "source_id": r[11], "mail_indexed": r[12], "status": r[13]}
            for r in cur.fetchall()
        ]

        cur.execute("""
            SELECT project_name, issue_status, COUNT(*)
            FROM mantis_issues
            GROUP BY project_name, issue_status
            ORDER BY project_name, COUNT(*) DESC
        """)
        mantis_stats = [
            {"project": r[0], "status": r[1], "count": r[2]}
            for r in cur.fetchall()
        ]

        cur.execute("""
            SELECT channel_title, COUNT(*), MAX(published_at)
            FROM youtube_videos
            GROUP BY channel_title
            ORDER BY COUNT(*) DESC
            LIMIT 20
        """)
        yt_stats = [
            {"channel": r[0], "count": r[1], "last_published": r[2]}
            for r in cur.fetchall()
        ]

        cur.execute("""
            SELECT status, COUNT(*) FROM omnifocus_tasks
            GROUP BY status ORDER BY COUNT(*) DESC
        """)
        omnifocus_stats = [{"status": r[0], "count": r[1]} for r in cur.fetchall()]

        cur.execute("""
            SELECT name, modified_at FROM apple_notes
            ORDER BY modified_at DESC NULLS LAST LIMIT 10
        """)
        notes_recent = [{"name": r[0] or "(bez názvu)", "modified_at": r[1]} for r in cur.fetchall()]

        cur.execute("""
            SELECT summary, calendar, start_at, end_at, location
            FROM calendar_events
            WHERE start_at > NOW()
            ORDER BY start_at ASC LIMIT 15
        """)
        calendar_upcoming = [
            {"summary": r[0], "calendar": r[1], "start_at": r[2],
             "end_at": r[3], "location": r[4]}
            for r in cur.fetchall()
        ]

        conn.close()
        return {"ok": True, "counts": counts, "recent_actions": recent_actions,
                "email_stats": email_stats, "rss_stats": rss_stats, "yt_stats": yt_stats,
                "mantis_stats": mantis_stats, "email_log": email_log,
                "omnifocus_stats": omnifocus_stats,
                "notes_recent": notes_recent, "calendar_upcoming": calendar_upcoming}
    except Exception as e:
        return {"ok": False, "error": str(e), "counts": {}, "recent_actions": [], "email_stats": [], "rss_stats": [], "yt_stats": [], "mantis_stats": [], "email_log": [], "omnifocus_stats": [], "notes_recent": [], "calendar_upcoming": []}


def get_chroma_status() -> dict:
    try:
        r = httpx.get(f"http://{CHROMA_HOST}:{CHROMA_PORT}/api/v2/heartbeat", timeout=3)
        return {"ok": r.status_code == 200}
    except Exception as e:
        return {"ok": False, "error": str(e)}


APPLE_BRIDGE_URL = os.getenv("APPLE_BRIDGE_URL", "http://host.docker.internal:9100")


def get_apple_bridge_status() -> dict:
    try:
        r = httpx.get(f"{APPLE_BRIDGE_URL}/health", timeout=3)
        return {"ok": r.status_code == 200}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    db = get_db_status()
    chroma = get_chroma_status()
    apple = get_apple_bridge_status()
    imap_rows = []
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute("""
            SELECT account, login_ok, login_checked_at, idle_state, idle_last_seen, idle_last_push, error_msg
            FROM imap_status ORDER BY account
        """)
        from datetime import timezone as _tz
        now_utc = datetime.now(_tz.utc)
        for r in cur.fetchall():
            idle_age = (now_utc - r[4].replace(tzinfo=_tz.utc)).total_seconds() if r[4] else None
            state = r[3]
            if not r[1]:
                dot = "red"
            elif state == "no_idle":
                dot = "orange"
            elif state == "active" and idle_age is not None and idle_age < 1800:
                dot = "green"
            elif state == "reconnecting":
                dot = "orange"
            else:
                dot = "orange"
            imap_rows.append({
                "account": r[0],
                "dot": dot,
                "idle_state": state or "?",
                "error": r[6],
            })
        conn.close()
    except Exception:
        pass
    return templates.TemplateResponse("index.html", {
        "request": request,
        "db": db,
        "chroma": chroma,
        "apple": apple,
        "imap_rows": imap_rows,
        "now": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "rss_stats": db.get("rss_stats", []),
        "yt_stats": db.get("yt_stats", []),
    })


FIRMA_OPTIONS    = ["DXPSOLUTIONS", "MBANK", "ZAMECNICTVI", "PRIVATE"]
TYP_OPTIONS      = ["SPAM", "NABÍDKA", "ÚKOL", "INFO", "FAKTURA", "POTVRZENÍ", "NEWSLETTER", "NOTIFIKACE", "ESHOP"]
TASK_OPTIONS     = ["ČEKÁ-NA-MĚ", "ČEKÁ-NA-ODPOVĚĎ", "→OF", "→REM", "HOTOVO", ""]


@app.get("/api/email/{email_id}")
async def api_email_detail(email_id: str):
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute("""
            SELECT id, mailbox, from_address, subject, sent_at,
                   firma, typ, task_status, is_spam, ai_confidence, human_reviewed,
                   unsubscribe_url, body_text
            FROM email_messages WHERE id = %s
        """, (email_id,))
        r = cur.fetchone()
        conn.close()
        if not r:
            raise HTTPException(status_code=404, detail="Email nenalezen")
        return {
            "id": str(r[0]), "mailbox": r[1], "from_address": r[2],
            "subject": r[3], "sent_at": r[4].isoformat() if r[4] else None,
            "firma": r[5], "typ": r[6], "task_status": r[7],
            "is_spam": r[8], "confidence": r[9], "human_reviewed": r[10],
            "unsubscribe_url": r[11],
            "body_preview": (r[12] or "")[:300] if r[12] else None,
            "firma_options": FIRMA_OPTIONS, "typ_options": TYP_OPTIONS, "task_options": TASK_OPTIONS,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class TagUpdate(BaseModel):
    firma: str | None = None
    typ: str | None = None
    task_status: str | None = None
    is_spam: bool | None = None


@app.post("/api/email/{email_id}/unsubscribe")
async def api_email_unsubscribe(email_id: str):
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute("SELECT from_address FROM email_messages WHERE id=%s", (email_id,))
        row = cur.fetchone()
        if row:
            from_addr = row[0]
            cur.execute("""
                UPDATE email_messages SET is_spam=TRUE, human_reviewed=TRUE, status='unsubscribed'
                WHERE from_address=%s
            """, (from_addr,))
            cur.execute("""
                INSERT INTO classification_rules (rule_type, match_field, match_value, result_value)
                VALUES ('spam', 'from_address', %s, 'yes')
                ON CONFLICT (rule_type, match_field, match_value) DO UPDATE
                    SET result_value='yes', hit_count=classification_rules.hit_count+1, updated_at=NOW()
            """, (from_addr,))
        conn.commit()
        conn.close()
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/email/{email_id}/tags")
async def api_email_update_tags(email_id: str, body: TagUpdate):
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute("""
            UPDATE email_messages SET
                firma = COALESCE(%s, firma),
                typ = COALESCE(%s, typ),
                task_status = %s,
                is_spam = COALESCE(%s, is_spam),
                human_reviewed = TRUE, status = 'reviewed'
            WHERE id = %s
            RETURNING from_address
        """, (body.firma, body.typ, body.task_status or None, body.is_spam, email_id))
        row = cur.fetchone()
        if row and body.firma:
            from_addr = row[0]
            for field, val in [("firma", body.firma), ("typ", body.typ)]:
                if val:
                    cur.execute("""
                        INSERT INTO classification_rules (rule_type, match_field, match_value, result_value)
                        VALUES (%s, 'from_address', %s, %s)
                        ON CONFLICT (rule_type, match_field, match_value) DO UPDATE
                            SET result_value=EXCLUDED.result_value, hit_count=classification_rules.hit_count+1, updated_at=NOW()
                    """, (field, from_addr, val))
        conn.commit()
        conn.close()
        # IMAP akce přes ingest API
        try:
            if body.is_spam:
                httpx.post(f"{INGEST_URL}/email/{email_id}/move-trash", timeout=10)
            else:
                httpx.post(f"{INGEST_URL}/email/{email_id}/mark-read", timeout=10)
        except Exception:
            pass
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/obsah", response_class=HTMLResponse)
async def obsah(request: Request):
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute("""
            WITH signals AS (
                SELECT t.id as tid, t.name as tname, t.parent_id,
                       array_agg(lower(s.value)) as vals
                FROM topics t
                JOIN topic_signals s ON s.topic_id = t.id
                GROUP BY t.id, t.name, t.parent_id
            ),
            scored AS (
                SELECT v.id, v.title, v.channel_title, v.published_at, v.url,
                       s.tid, s.tname, s.parent_id,
                       (SELECT count(*) FROM unnest(s.vals) val
                        WHERE lower(v.title || ' ' || coalesce(v.description,'') || ' ' || coalesce(v.channel_title,''))
                              LIKE '%' || val || '%') as score
                FROM youtube_videos v
                CROSS JOIN signals s
            ),
            best AS (
                SELECT DISTINCT ON (id) id, title, channel_title, published_at, url, tid, tname, score
                FROM scored WHERE score > 0
                ORDER BY id, score DESC
            )
            SELECT score, tid, tname, channel_title, title, published_at, url
            FROM best ORDER BY tid, score DESC, published_at DESC
        """)
        rows = cur.fetchall()

        cur.execute("SELECT id, name, parent_id FROM topics ORDER BY parent_id NULLS FIRST, name")
        all_topics = [{"id": r[0], "name": r[1], "parent_id": r[2]} for r in cur.fetchall()]
        conn.close()

        from collections import defaultdict
        by_topic = defaultdict(list)
        for score, tid, tname, channel, title, pub, url in rows:
            by_topic[tid].append({"score": score, "channel": channel, "title": title, "published_at": pub, "url": url})

        topic_map = {t["id"]: {**t, "videos": by_topic.get(t["id"], [])[:20],
                                "total": len(by_topic.get(t["id"], [])), "children": []}
                     for t in all_topics}
        topics_out = []
        for t in topic_map.values():
            if t["parent_id"] and t["parent_id"] in topic_map:
                topic_map[t["parent_id"]]["children"].append(t)
            elif t["parent_id"] is None:
                topics_out.append(t)
        # filtruj — zobraz jen pokud má videa nebo alespoň jedno dítě s videi
        def has_content(t):
            return t["total"] > 0 or any(c["total"] > 0 for c in t["children"])
        topics_out = [t for t in topics_out if has_content(t)]
    except Exception as e:
        topics_out = []
    return templates.TemplateResponse("obsah.html", {
        "request": request, "topics": topics_out,
        "now": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })


@app.get("/pravidla", response_class=HTMLResponse)
async def pravidla(request: Request):
    rules = []
    decision_rules = []
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute("SELECT id, rule_type, match_field, match_value, result_value, confidence, hit_count, updated_at FROM classification_rules ORDER BY hit_count DESC, updated_at DESC")
        rules = [{"id": r[0], "rule_type": r[1], "match_field": r[2], "match_value": r[3],
                  "result_value": r[4], "confidence": r[5], "hit_count": r[6], "updated_at": r[7]} for r in cur.fetchall()]
        # M4: decision_rules engine
        try:
            cur.execute("""
                SELECT id, priority, rule_name, condition_type, condition_value,
                       action_type, action_value, enabled, description, updated_at
                FROM decision_rules ORDER BY priority ASC, id ASC
            """)
            import json as _json
            decision_rules = [{
                "id": r[0], "priority": r[1], "rule_name": r[2],
                "condition_type": r[3],
                "condition_value": _json.dumps(r[4], ensure_ascii=False),
                "action_type": r[5],
                "action_value": _json.dumps(r[6], ensure_ascii=False),
                "enabled": r[7], "description": r[8] or "",
                "updated_at": r[9].strftime("%Y-%m-%d %H:%M") if r[9] else "",
            } for r in cur.fetchall()]
        except Exception:
            decision_rules = []
        conn.close()
    except Exception:
        rules = []
    return templates.TemplateResponse("pravidla.html", {
        "request": request, "rules": rules, "decision_rules": decision_rules,
        "now": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })


# ===== M4: Decision Rules CRUD API =====

class DecisionRuleIn(BaseModel):
    priority: int
    rule_name: str
    condition_type: str
    condition_value: dict | list
    action_type: str
    action_value: dict | list
    enabled: bool = True
    description: str | None = None


@app.post("/api/decision-rules")
async def api_decision_rule_create(payload: DecisionRuleIn):
    import json as _json
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO decision_rules (priority, rule_name, condition_type, condition_value,
                                        action_type, action_value, enabled, description)
            VALUES (%s, %s, %s, %s::jsonb, %s, %s::jsonb, %s, %s)
            RETURNING id
        """, (payload.priority, payload.rule_name, payload.condition_type,
              _json.dumps(payload.condition_value), payload.action_type,
              _json.dumps(payload.action_value), payload.enabled, payload.description))
        new_id = cur.fetchone()[0]
        conn.commit()
        conn.close()
        return {"ok": True, "id": new_id}
    except psycopg2.errors.UniqueViolation:
        raise HTTPException(status_code=409, detail=f"rule_name '{payload.rule_name}' už existuje")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.put("/api/decision-rules/{rule_id}")
async def api_decision_rule_update(rule_id: int, payload: DecisionRuleIn):
    import json as _json
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute("""
            UPDATE decision_rules
            SET priority=%s, rule_name=%s, condition_type=%s, condition_value=%s::jsonb,
                action_type=%s, action_value=%s::jsonb, enabled=%s, description=%s,
                updated_at=NOW()
            WHERE id=%s
            RETURNING id
        """, (payload.priority, payload.rule_name, payload.condition_type,
              _json.dumps(payload.condition_value), payload.action_type,
              _json.dumps(payload.action_value), payload.enabled, payload.description,
              rule_id))
        row = cur.fetchone()
        conn.commit()
        conn.close()
        if not row:
            raise HTTPException(status_code=404, detail="Pravidlo nenalezeno")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.patch("/api/decision-rules/{rule_id}/toggle")
async def api_decision_rule_toggle(rule_id: int):
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute("UPDATE decision_rules SET enabled = NOT enabled, updated_at=NOW() WHERE id=%s RETURNING enabled",
                    (rule_id,))
        row = cur.fetchone()
        conn.commit()
        conn.close()
        if not row:
            raise HTTPException(status_code=404, detail="Pravidlo nenalezeno")
        return {"ok": True, "enabled": row[0]}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


class DecisionRuleReorder(BaseModel):
    ids: list[int]


@app.patch("/api/decision-rules/reorder")
async def api_decision_rule_reorder(payload: DecisionRuleReorder):
    """P2: drag&drop reorder — přepočítá priority na 10, 20, 30, ...
    podle pořadí ID v payloadu (top → bottom v UI tabulce)."""
    if not payload.ids:
        raise HTTPException(status_code=400, detail="ids prázdný")
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        new_priorities = {}
        for idx, rid in enumerate(payload.ids):
            new_prio = (idx + 1) * 10
            cur.execute("UPDATE decision_rules SET priority=%s, updated_at=NOW() WHERE id=%s RETURNING id",
                        (new_prio, rid))
            if cur.fetchone():
                new_priorities[rid] = new_prio
        conn.commit()
        conn.close()
        return {"ok": True, "priorities": new_priorities}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.delete("/api/decision-rules/{rule_id}")
async def api_decision_rule_delete(rule_id: int):
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute("DELETE FROM decision_rules WHERE id=%s RETURNING id", (rule_id,))
        row = cur.fetchone()
        conn.commit()
        conn.close()
        if not row:
            raise HTTPException(status_code=404, detail="Pravidlo nenalezeno")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/ukoly", response_class=HTMLResponse)
async def ukoly(request: Request):
    pending = []
    emails = []
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute("""
            SELECT id, source_type, action_type, status, created_at, action_payload
            FROM actions WHERE status IN ('pending', 'proposed')
            ORDER BY created_at DESC LIMIT 50
        """)
        pending = [{"id": str(r[0]), "source_type": r[1], "action_type": r[2],
                    "status": r[3], "created_at": r[4], "payload": r[5]} for r in cur.fetchall()]
        cur.execute("""
            SELECT id, mailbox, from_address, subject, typ, firma, ai_confidence, sent_at, tg_notified_at
            FROM email_messages
            WHERE human_reviewed = FALSE
              AND is_spam = FALSE
              AND typ IS NOT NULL
              AND typ NOT IN ('SPAM', 'ESHOP')
              AND tg_notified_at IS NOT NULL
            ORDER BY sent_at DESC
            LIMIT 100
        """)
        emails = [{"id": str(r[0]), "mailbox": (r[1] or "").split("@")[0],
                   "from_address": r[2] or "", "subject": r[3] or "(bez předmětu)",
                   "typ": r[4], "firma": r[5] or "",
                   "confidence": f"{int((r[6] or 0)*100)}%",
                   "sent_at": r[7], "notified": r[8] is not None,
                   "suggested": None} for r in cur.fetchall()]
        conn.close()

        # Chroma predikce per email (batch call do ingest API).
        # Pokud selže nebo timeout, prostě bez návrhů — UI funguje dál.
        if emails:
            try:
                ids = [e["id"] for e in emails]
                r = httpx.post(f"{INGEST_URL}/emails/suggested",
                               json={"ids": ids}, timeout=10)
                if r.status_code == 200:
                    sug_map = r.json() or {}
                    for e in emails:
                        e["suggested"] = sug_map.get(e["id"])
            except Exception as _se:
                import logging as _log
                _log.getLogger("ukoly").warning(f"emails/suggested fail: {_se}")
    except Exception as _e:
        import logging as _log
        _log.getLogger("ukoly").error(f"Ukoly route chyba: {_e}")
    return templates.TemplateResponse("ukoly.html", {
        "request": request, "pending": pending, "emails": emails,
        "now": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })


@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute("SELECT id, name, parent_id, priority, description FROM topics ORDER BY parent_id NULLS FIRST, name")
        topics_raw = cur.fetchall()
        cur.execute("SELECT id, topic_id, signal_type, value FROM topic_signals ORDER BY signal_type, value")
        signals_raw = cur.fetchall()
        conn.close()
        topics = [{"id": r[0], "name": r[1], "parent_id": r[2], "priority": r[3], "description": r[4]} for r in topics_raw]
        signals = {}
        for r in signals_raw:
            signals.setdefault(r[1], []).append({"id": r[0], "type": r[2], "value": r[3]})
        for t in topics:
            t["signals"] = signals.get(t["id"], [])
        parents = [t for t in topics if t["parent_id"] is None]
        for p in parents:
            p["children"] = [t for t in topics if t["parent_id"] == p["id"]]
    except Exception as e:
        parents = []
        topics = []
    return templates.TemplateResponse("admin.html", {
        "request": request, "topics": parents, "all_topics": topics,
        "now": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })


class TopicCreate(BaseModel):
    name: str
    parent_id: int | None = None
    priority: str = "medium"
    description: str | None = None

class SignalCreate(BaseModel):
    signal_type: str
    value: str


@app.post("/api/topics")
async def api_topic_create(body: TopicCreate):
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute("INSERT INTO topics (name, parent_id, priority, description) VALUES (%s,%s,%s,%s) RETURNING id",
                    (body.name.strip(), body.parent_id, body.priority, body.description))
        new_id = cur.fetchone()[0]
        conn.commit(); conn.close()
        return {"ok": True, "id": new_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/topics/{topic_id}")
async def api_topic_delete(topic_id: int):
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute("DELETE FROM topics WHERE id=%s", (topic_id,))
        conn.commit(); conn.close()
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/topics/{topic_id}/signals")
async def api_signal_create(topic_id: int, body: SignalCreate):
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute("INSERT INTO topic_signals (topic_id, signal_type, value) VALUES (%s,%s,%s) RETURNING id",
                    (topic_id, body.signal_type, body.value.strip()))
        new_id = cur.fetchone()[0]
        conn.commit(); conn.close()
        return {"ok": True, "id": new_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/api/signals/{signal_id}")
async def api_signal_delete(signal_id: int):
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute("DELETE FROM topic_signals WHERE id=%s", (signal_id,))
        conn.commit(); conn.close()
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/email/{email_id}/mark-not-indexed")
async def mark_email_not_indexed(email_id: str):
    """Označí email jako mail_indexed=FALSE (volá frontend po 404 z mail-bridge /open)."""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute("""
            UPDATE email_messages
               SET mail_indexed = FALSE,
                   mail_indexed_checked_at = now()
             WHERE id = %s
            RETURNING id
        """, (email_id,))
        row = cur.fetchone()
        conn.commit()
        conn.close()
        if not row:
            raise HTTPException(status_code=404, detail="email not found")
        return {"ok": True, "id": str(row[0])}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/imap-status")
async def imap_status():
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cur = conn.cursor()
        cur.execute("""
            SELECT account, login_ok, login_checked_at, idle_state, idle_last_seen, idle_last_push, error_msg
            FROM imap_status ORDER BY account
        """)
        rows = cur.fetchall()
        conn.close()
        return [{"account": r[0], "login_ok": r[1],
                 "login_checked_at": r[2].isoformat() if r[2] else None,
                 "idle_state": r[3],
                 "idle_last_seen": r[4].isoformat() if r[4] else None,
                 "idle_last_push": r[5].isoformat() if r[5] else None,
                 "error_msg": r[6]} for r in rows]
    except Exception as e:
        return []


@app.get("/api/status")
async def api_status():
    return {
        "db": get_db_status(),
        "chroma": get_chroma_status(),
        "timestamp": datetime.now().isoformat(),
    }


INGEST_API = os.getenv("INGEST_API_URL", "http://brogi_scheduler:9001")

@app.post("/api/ingest/email/{email_id}/action/{action}")
async def proxy_email_action(email_id: str, action: str):
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(f"{INGEST_URL}/email/{email_id}/action/{action}")
            return r.json()
    except Exception as e:
        return JSONResponse(status_code=502, content={"ok": False, "detail": str(e)})


@app.post("/api/fetch-now")
async def fetch_now():
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(f"{INGEST_API}/fetch-now")
            r.raise_for_status()
            return r.json()
    except Exception as e:
        return JSONResponse(status_code=502, content={"status": "error", "detail": str(e)})


# ─────────────────────────────────────────
#  CHROMA — naučené vzory
# ─────────────────────────────────────────

_CHROMA_BASE = f"http://{CHROMA_HOST}:{CHROMA_PORT}/api/v2/tenants/default_tenant/databases/default_database"
_CHROMA_COL_NAME = "email_actions"
_chroma_col_id_cache: str | None = None


async def _chroma_col_id() -> str:
    global _chroma_col_id_cache
    if _chroma_col_id_cache:
        return _chroma_col_id_cache
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"{_CHROMA_BASE}/collections/{_CHROMA_COL_NAME}")
        r.raise_for_status()
        _chroma_col_id_cache = r.json()["id"]
        return _chroma_col_id_cache


async def _chroma_get(offset: int = 0, limit: int = 25) -> dict:
    col_id = await _chroma_col_id()
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(
            f"{_CHROMA_BASE}/collections/{col_id}/get",
            json={"limit": limit, "offset": offset, "include": ["metadatas", "documents"]},
        )
        r.raise_for_status()
        return r.json()


async def _chroma_count() -> int:
    col_id = await _chroma_col_id()
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(f"{_CHROMA_BASE}/collections/{col_id}/count")
        r.raise_for_status()
        return int(r.json())


async def _chroma_get_all(limit: int = 500) -> dict:
    """Načte všechny záznamy najednou (pro JS filtrování)."""
    col_id = await _chroma_col_id()
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(
            f"{_CHROMA_BASE}/collections/{col_id}/get",
            json={"limit": limit, "offset": 0, "include": ["metadatas", "documents"]},
        )
        r.raise_for_status()
        return r.json()


@app.get("/chroma", response_class=HTMLResponse)
async def page_chroma(request: Request):
    try:
        total = await _chroma_count()
        data  = await _chroma_get_all(min(total + 10, 500))
        ids   = data.get("ids", []) or []
        metas = data.get("metadatas", []) or []
        records = []
        for i, rec_id in enumerate(ids):
            meta = metas[i] if i < len(metas) else {}
            ts = (meta.get("timestamp", "") or "")[:10]
            records.append({
                "id":       rec_id,
                "from_addr": meta.get("from_addr", ""),
                "subject":  meta.get("subject", ""),
                "action":   meta.get("action", ""),
                "typ":      meta.get("typ", ""),
                "mailbox":  (meta.get("mailbox", "") or "").split("@")[0],
                "human":    bool(meta.get("human_corrected", False)),
                "ts":       ts,
            })
        # Unikátní hodnoty pro filtry
        actions = sorted(set(r["action"] for r in records if r["action"]))
        typy    = sorted(set(r["typ"]    for r in records if r["typ"]))
    except Exception as e:
        records, total, actions, typy = [], 0, [], []
    return templates.TemplateResponse("chroma.html", {
        "request": request, "records": records,
        "total": total, "actions": actions, "typy": typy,
    })


@app.delete("/api/chroma/{record_id}")
async def api_chroma_delete(record_id: str):
    try:
        col_id = await _chroma_col_id()
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                f"{_CHROMA_BASE}/collections/{col_id}/delete",
                json={"ids": [record_id]},
            )
            r.raise_for_status()
        return {"ok": True}
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "detail": str(e)})


@app.patch("/api/chroma/{record_id}")
async def api_chroma_edit(record_id: str, body: dict):
    """Změní action záznamu: načte embedding, smaže, znovu uloží s novou akcí."""
    new_action = body.get("action", "").strip()
    if not new_action:
        raise HTTPException(status_code=422, detail="action required")
    try:
        col_id = await _chroma_col_id()
        async with httpx.AsyncClient(timeout=15) as client:
            # Načti záznam včetně embeddingu
            r = await client.post(
                f"{_CHROMA_BASE}/collections/{col_id}/get",
                json={"ids": [record_id], "include": ["metadatas", "documents", "embeddings"]},
            )
            r.raise_for_status()
            data = r.json()
            if not data.get("ids"):
                raise HTTPException(status_code=404, detail="záznam nenalezen")
            meta      = data["metadatas"][0]
            doc       = data["documents"][0]
            embedding = data["embeddings"][0]
            # Uprav action v metadatech
            meta["action"] = new_action
            meta["human_corrected"] = True
            # Smaž starý
            await client.post(
                f"{_CHROMA_BASE}/collections/{col_id}/delete",
                json={"ids": [record_id]},
            )
            # Vlož nový se stejným ID a embeddingem
            r2 = await client.post(
                f"{_CHROMA_BASE}/collections/{col_id}/upsert",
                json={"ids": [record_id], "embeddings": [embedding],
                      "documents": [doc], "metadatas": [meta]},
            )
            r2.raise_for_status()
        return {"ok": True, "action": new_action}
    except HTTPException:
        raise
    except Exception as e:
        return JSONResponse(status_code=500, content={"ok": False, "detail": str(e)})

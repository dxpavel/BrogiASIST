"""
Pending actions queue worker — degraded mode pro Apple Bridge offline.

Per docs/brogiasist-semantics-v1.md sekce 9.

Když Apple Bridge dočasně padá (Mac Studio sleep, fork-bug regrese, restart),
HTTP volání z _bridge_call selžou. Místo ztráty in-flight akcí (2of, 2cal,
2note, 2rem) je zapíšeme do pending_actions tabulky. Worker periodicky čte
pending záznamy, volá Bridge, throttle 2s mezi akcemi.

Po 3 selháních (attempts ≥ 3) označí akci status='failed' + TG alert
Pavlovi.
"""

import os
import time
import json
import logging
import httpx
from db import get_conn
from telegram_notify import send as tg_send

log = logging.getLogger(__name__)

BRIDGE_URL = os.getenv("APPLE_BRIDGE_URL", "http://host.docker.internal:9100")
DRAIN_BATCH = 20         # max akcí per drain cyklus
DRAIN_THROTTLE = 2.0     # sekund mezi akcemi (per spec M3)
MAX_ATTEMPTS = 3


# ─────────────────────────────────────────────────────────────────────────
# Bridge health
# ─────────────────────────────────────────────────────────────────────────

def bridge_health() -> bool:
    """Aktivní /health ping. True pokud Apple Bridge odpovídá < 5s."""
    try:
        r = httpx.get(f"{BRIDGE_URL}/health", timeout=5)
        return r.status_code == 200 and r.json().get("ok") is True
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────────────────
# Enqueue (volá se z _bridge_call při unreachable)
# ─────────────────────────────────────────────────────────────────────────

def enqueue(email_id: str, action: str, path: str, payload: dict) -> int:
    """Zapíše akci do pending_actions queue. Vrací id záznamu."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO pending_actions (email_id, action, action_data, status)
        VALUES (%s, %s, %s::jsonb, 'pending')
        RETURNING id
    """, (email_id, action, json.dumps({"path": path, "payload": payload})))
    pid = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    log.info(f"enqueued pending_action #{pid}: email={email_id} action={action} path={path}")
    return pid


# ─────────────────────────────────────────────────────────────────────────
# Drain (volá se ze scheduleru každou minutu)
# ─────────────────────────────────────────────────────────────────────────

def drain_queue():
    """Zpracuje pending akce. Pokud Bridge offline → no-op (zkusíme příště).
    Throttle 2s mezi akcemi (spec M3, aby Apple Studio nebyl přetížený)."""
    if not bridge_health():
        # Bridge offline — žádné akce nezpracujeme. Loguj jen pokud queue není prázdná.
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT count(*) FROM pending_actions WHERE status = 'pending'")
        pending_count = cur.fetchone()[0]
        cur.close()
        conn.close()
        if pending_count > 0:
            log.warning(f"drain_queue: Apple Bridge offline, {pending_count} akcí čeká")
        return

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, email_id, action, action_data, attempts
        FROM pending_actions
        WHERE status = 'pending'
        ORDER BY created_at ASC
        LIMIT %s
    """, (DRAIN_BATCH,))
    rows = cur.fetchall()
    cur.close()
    conn.close()

    if not rows:
        return

    log.info(f"drain_queue: {len(rows)} akcí k zpracování")

    for pid, email_id, action, action_data, attempts in rows:
        try:
            data = action_data if isinstance(action_data, dict) else json.loads(action_data)
            path = data.get("path")
            payload = data.get("payload", {})
        except Exception as e:
            _mark_failed(pid, f"invalid action_data: {e}")
            continue

        # Označit processing (race-safe)
        _set_status(pid, "processing", attempts + 1)

        try:
            r = httpx.post(f"{BRIDGE_URL}{path}", json=payload, timeout=120)
            if r.status_code == 200:
                _set_status(pid, "done", None)
                log.info(f"drain: pending #{pid} ({action}) → OK")
            else:
                _handle_fail(pid, attempts + 1, action, f"HTTP {r.status_code}: {r.text[:200]}")
        except Exception as e:
            _handle_fail(pid, attempts + 1, action, str(e))

        time.sleep(DRAIN_THROTTLE)


# ─────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────

def _set_status(pid: int, status: str, attempts: int | None):
    conn = get_conn()
    cur = conn.cursor()
    if attempts is not None:
        cur.execute(
            "UPDATE pending_actions SET status=%s, attempts=%s, last_attempt_at=NOW() WHERE id=%s",
            (status, attempts, pid)
        )
    else:
        cur.execute(
            "UPDATE pending_actions SET status=%s, last_attempt_at=NOW() WHERE id=%s",
            (status, pid)
        )
    conn.commit()
    cur.close()
    conn.close()


def _mark_failed(pid: int, reason: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE pending_actions SET status='failed', last_error=%s, last_attempt_at=NOW() WHERE id=%s",
        (reason[:500], pid)
    )
    conn.commit()
    cur.close()
    conn.close()


def _handle_fail(pid: int, attempts: int, action: str, error: str):
    if attempts >= MAX_ATTEMPTS:
        _mark_failed(pid, error)
        log.error(f"drain: pending #{pid} ({action}) → FAILED po {attempts} pokusech: {error}")
        try:
            tg_send(f"❌ <b>Akce {action} selhala</b> po {attempts} pokusech\n<code>{error[:300]}</code>")
        except Exception:
            pass
    else:
        _set_status(pid, "pending", attempts)
        # Update last_error
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("UPDATE pending_actions SET last_error=%s WHERE id=%s", (error[:500], pid))
        conn.commit()
        cur.close()
        conn.close()
        log.warning(f"drain: pending #{pid} ({action}) → retry {attempts}/{MAX_ATTEMPTS}: {error}")

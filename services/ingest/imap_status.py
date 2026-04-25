"""
BrogiASIST — IMAP status tracker
Zapíše login test + IDLE heartbeat do DB tabulky imap_status.
"""
import logging
from datetime import datetime, timezone
from db import get_conn
from ingest_email import ACCOUNTS, connect

log = logging.getLogger(__name__)


def _upsert(account: str, **kwargs):
    now = datetime.now(tz=timezone.utc)
    conn = get_conn()
    cur = conn.cursor()
    cols = ["account"] + list(kwargs.keys())
    vals = [account] + list(kwargs.values())
    placeholders = ", ".join(["%s"] * len(vals))
    updates = ", ".join(f"{k}=EXCLUDED.{k}" for k in kwargs.keys())
    cur.execute(
        f"INSERT INTO imap_status ({', '.join(cols)}) VALUES ({placeholders}) "
        f"ON CONFLICT (account) DO UPDATE SET {updates}",
        vals
    )
    conn.commit()
    cur.close()
    conn.close()


def _now():
    return datetime.now(tz=timezone.utc)


def set_login(account: str, ok: bool, error: str = None):
    _upsert(account, login_ok=ok, login_checked_at=_now(), error_msg=error)


def set_idle_state(account: str, state: str):
    _upsert(account, idle_state=state, idle_last_seen=_now())


def set_idle_push(account: str):
    _upsert(account, idle_state="active", idle_last_seen=_now(), idle_last_push=_now())


def job_imap_login_check():
    """Scheduler job — otestuje LOGIN pro každý účet (každých 5 min)."""
    for acc in ACCOUNTS:
        name = acc["name"]
        try:
            m = connect(acc)
            m.logout()
            set_login(name, True)
            log.info(f"IMAP login OK: {name}")
        except Exception as e:
            set_login(name, False, str(e)[:200])
            log.warning(f"IMAP login FAIL: {name}: {e}")

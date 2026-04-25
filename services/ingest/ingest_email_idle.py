"""
Email ingest — IMAP IDLE (push)
Každý účet běží ve vlastním threadu. Server pošle signál při nové zprávě.
IDLE timeout 28 min → reconnect (RFC 2177 doporučuje max 29 min).
"""

import os
import time
import logging
import threading
from datetime import datetime, timezone, timedelta
from imapclient import IMAPClient
from dotenv import load_dotenv
from ingest_email import ACCOUNTS, fetch_messages, upsert_messages
from imap_status import set_idle_state, set_idle_push

load_dotenv(os.path.join(os.path.dirname(__file__), "../../.env"))

log = logging.getLogger("email_idle")
IDLE_TIMEOUT = 28 * 60   # 28 minut v sekundách
DAYS_BACK = 7


def connect_idle(account: dict) -> IMAPClient:
    ssl = account.get("ssl", True)
    client = IMAPClient(account["host"], port=account["port"], ssl=ssl, use_uid=True)
    if not ssl:
        client.starttls()
    client.login(account["user"], account["password"])
    client.select_folder("INBOX")
    return client


def run_idle_loop(account: dict):
    name = account["name"]
    log.info(f"[{name}] IDLE listener start")

    while True:
        try:
            client = connect_idle(account)

            # Při startu stáhni co je nového za 7 dní
            since = datetime.now(tz=timezone.utc) - timedelta(days=DAYS_BACK)
            msgs = fetch_messages(account, since)
            new_c, _ = upsert_messages(msgs)
            if new_c:
                log.info(f"[{name}] Initial fetch: +{new_c} nových")

            client.idle()
            log.info(f"[{name}] IDLE aktivní")
            set_idle_state(name, "active")

            while True:
                responses = client.idle_check(timeout=IDLE_TIMEOUT)

                if responses:
                    has_new = any(
                        b"EXISTS" in str(r).encode() or (isinstance(r, tuple) and r[1] == b"EXISTS")
                        for r in responses
                    )
                    if has_new or responses:
                        client.idle_done()
                        since = datetime.now(tz=timezone.utc) - timedelta(minutes=5)
                        msgs = fetch_messages(account, since)
                        new_c, _ = upsert_messages(msgs)
                        if new_c:
                            log.info(f"[{name}] PUSH: +{new_c} nových zpráv")
                            set_idle_push(name)
                        else:
                            set_idle_state(name, "active")
                        client.idle()
                else:
                    # Timeout → reconnect (IDLE max 29 min per RFC)
                    log.debug(f"[{name}] IDLE timeout → reconnect")
                    client.idle_done()
                    client.logout()
                    break

        except Exception as e:
            log.error(f"[{name}] Chyba: {e} — reconnect za 30s")
            set_idle_state(name, "reconnecting")
            time.sleep(30)


def start_all():
    threads = []
    for account in ACCOUNTS:
        if not account.get("supports_idle", True):
            log.info(f"[{account['name']}] IDLE nepodporováno — přeskočeno (záloha: 30min scan)")
            set_idle_state(account["name"], "no_idle")
            continue
        t = threading.Thread(
            target=run_idle_loop,
            args=(account,),
            name=f"idle-{account['name']}",
            daemon=True,
        )
        t.start()
        threads.append(t)
        time.sleep(1)  # malá pauza mezi připojeními
    return threads


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    threads = start_all()
    log.info(f"IDLE listeners aktivní pro {len(threads)} účtů")
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        log.info("Ukončuji...")

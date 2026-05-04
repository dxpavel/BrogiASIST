"""
M1 smoke test pro smtp_send modul.

Spuštění (v scheduler containeru):
  docker exec brogiasist-scheduler python /app/test_smtp_send.py

Pošle test email z dxpavel@gmail.com sám sobě s X-Brogi-Auto headerem.
Ověření:
1. Email dorazí (Gmail inbox)
2. APPEND do [Gmail]/Sent Mail proběhl (Pavel ho vidí v Sent)
3. Když IMAP IDLE / 30min scan zachytí appended kopii, decision_engine
   self_sent rule (priority 5) ji skipne → email se NEKLASIFIKUJE,
   neobjeví se v TG.
"""
import sys
import logging

sys.path.insert(0, "/app")

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("test")

from smtp_send import send_reply

ok, mid, err = send_reply(
    account_name="dxpavel@gmail.com",
    to="dxpavel@gmail.com",
    subject="[BrogiASIST M1 smoke] X-Brogi-Auto end-to-end test",
    body=(
        "M1 smoke test — smtp_send modul.\n\n"
        "Pokud je toto v Sent folderu (Gmail web → Sent), APPEND funguje.\n"
        "Pokud se NEZOBRAZÍ jako úkol v TG, decision rule self_sent funguje.\n\n"
        "X-Brogi-Auto: smoke-test\n"
    ),
    x_brogi_auto="smoke-test",
)

if ok:
    log.info(f"✓ send_reply OK: message_id={mid}")
else:
    log.error(f"✗ send_reply FAILED: {err}")
    sys.exit(1)

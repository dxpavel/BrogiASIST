"""
BrogiASIST — Telegram notifikace + callback handler
"""
import os
import httpx
import logging
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "../../.env"))

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
BASE = f"https://api.telegram.org/bot{TOKEN}"

log = logging.getLogger(__name__)


def send(text: str, buttons: list[list[dict]] = None) -> dict | None:
    """Pošle zprávu Pavlovi. buttons = [[{"text": "✅ OK", "callback_data": "ok:123"}]]"""
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}
    if buttons:
        payload["reply_markup"] = {"inline_keyboard": buttons}
    try:
        r = httpx.post(f"{BASE}/sendMessage", json=payload, timeout=10)
        r.raise_for_status()
        return r.json().get("result")
    except Exception as e:
        log.error(f"Telegram send: {e}")
        return None


def send_spam_check(email_id: int, from_addr: str, subject: str) -> dict | None:
    text = (
        f"🚨 <b>SPAM?</b>\n"
        f"Od: <code>{from_addr}</code>\n"
        f"Předmět: {subject}"
    )
    buttons = [[
        {"text": "🗑 SPAM", "callback_data": f"spam:yes:{email_id}"},
        {"text": "✅ Není spam", "callback_data": f"spam:no:{email_id}"},
    ]]
    return send(text, buttons)


def send_invoice_notify(vendor: str, amount: str, entity: str, of_task: str = None) -> dict | None:
    text = (
        f"📄 <b>Faktura k zaplacení</b>\n"
        f"Dodavatel: <b>{vendor}</b>\n"
        f"Částka: <b>{amount}</b>\n"
        f"Entita: {entity}\n"
        f"📥 Příloha na Ploše\n"
        + (f"✅ Přidáno do OmniFocus: <i>{of_task}</i>" if of_task else "")
    )
    return send(text)


def send_task_notify(source: str, task_name: str) -> dict | None:
    text = f"✅ <b>Nový úkol v OmniFocus</b>\n{source}\n<i>{task_name}</i>"
    return send(text)


def get_updates(offset: int = 0) -> list[dict]:
    try:
        r = httpx.get(f"{BASE}/getUpdates", params={"offset": offset, "timeout": 0}, timeout=10)
        r.raise_for_status()
        return r.json().get("result", [])
    except Exception as e:
        log.error(f"Telegram getUpdates: {e}")
        return []


def answer_callback(callback_query_id: str, text: str = "OK") -> None:
    try:
        httpx.post(f"{BASE}/answerCallbackQuery",
                   json={"callback_query_id": callback_query_id, "text": text}, timeout=5)
    except Exception:
        pass


def delete_message(message_id: int) -> bool:
    try:
        r = httpx.post(f"{BASE}/deleteMessage",
                       json={"chat_id": CHAT_ID, "message_id": message_id}, timeout=5)
        return r.ok
    except Exception:
        return False

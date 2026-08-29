#!/usr/bin/env python3
"""
Send config diff notification to Telegram.
"""

import os
import sys
import urllib.parse
import urllib.request

TG_API = "https://api.telegram.org/bot{token}/sendMessage"
CHUNK_SIZE = 3800
REQUEST_TIMEOUT = 20


def send_message(token: str, chat_id: str, text: str) -> None:
    """Send a message to Telegram, splitting into chunks if needed."""
    for start in range(0, len(text), CHUNK_SIZE):
        chunk = text[start : start + CHUNK_SIZE]
        payload = urllib.parse.urlencode(
            {
                "chat_id": chat_id,
                "text": chunk,
                "disable_web_page_preview": "true",
            }
        ).encode("utf-8")

        req = urllib.request.Request(
            TG_API.format(token=token),
            data=payload,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            result = resp.read().decode("utf-8")
            if '"ok":true' not in result:
                raise RuntimeError(f"Telegram API error: {result}")


def main() -> None:
    token = os.environ.get("TG_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TG_CHAT_ID", "").strip()
    first_run = os.environ.get("FIRST_RUN", "no") == "yes"

    if not token:
        raise SystemExit("TG_BOT_TOKEN is empty")
    if not chat_id:
        raise SystemExit("TG_CHAT_ID is empty")

    with open("/tmp/added.txt", encoding="utf-8") as f:
        added = f.read().splitlines()
    with open("/tmp/removed.txt", encoding="utf-8") as f:
        removed = f.read().splitlines()
    with open("configs.txt", encoding="utf-8") as f:
        total = sum(1 for line in f if line.strip())

    if first_run:
        message = (
            f"✅ ساب DGDreams با {total} کانفیگ راه‌اندازی شد.\n"
            "از این به بعد فقط تغییرات ارسال می‌شود."
        )
    else:
        message = "🔄 آپدیت ساب DGDreams\n"
        message += f"📦 تعداد فعلی: {total}\n\n"
        if added:
            message += f"➕ اضافه شد ({len(added)}):\n" + "\n".join(added) + "\n\n"
        if removed:
            message += f"➖ حذف شد ({len(removed)}):\n" + "\n".join(removed)

    send_message(token, chat_id, message)
    print("Telegram notification sent successfully")


if __name__ == "__main__":
    main()

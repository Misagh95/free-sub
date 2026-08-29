#!/usr/bin/env python3
"""
Send clean Telegram notification with subscription link.
"""

import os
import re
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone

TG_API = "https://api.telegram.org/bot{token}/sendMessage"
CHUNK_SIZE = 4000
REQUEST_TIMEOUT = 20

PROTOCOL_RE = re.compile(r"^(vless|vmess|trojan|ss|hysteria2|tuic)://", re.IGNORECASE)
FLAG_RE = re.compile(r"#DGDreams\s+(.+)$")

SUB_BASE_URL = "https://raw.githubusercontent.com/Misagh95/free-sub/main"


def send_message(token: str, chat_id: str, text: str, parse_mode: str = "HTML") -> None:
    for start in range(0, len(text), CHUNK_SIZE):
        chunk = text[start : start + CHUNK_SIZE]
        payload = urllib.parse.urlencode(
            {
                "chat_id": chat_id,
                "text": chunk,
                "parse_mode": parse_mode,
                "disable_web_page_preview": "true",
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            TG_API.format(token=token), data=payload, method="POST",
        )
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            result = resp.read().decode("utf-8")
            if '"ok":true' not in result:
                raise RuntimeError(f"Telegram API error: {result}")


def get_stats(configs: list[str]) -> tuple[Counter, Counter]:
    protocols = Counter(PROTOCOL_RE.match(c).group(1).lower() for c in configs if PROTOCOL_RE.match(c))
    flags = Counter(
        (m.group(1).strip() if (m := FLAG_RE.search(c)) else "🌐")
        for c in configs
    )
    return protocols, flags


def main() -> None:
    token = os.environ.get("TG_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TG_CHAT_ID", "").strip()
    first_run = os.environ.get("FIRST_RUN", "no") == "yes"
    sub_url = os.environ.get("SUB_URL", SUB_BASE_URL + "/configs_base64.txt").strip()

    if not token:
        raise SystemExit("TG_BOT_TOKEN is empty")
    if not chat_id:
        raise SystemExit("TG_CHAT_ID is empty")

    with open("/tmp/added.txt", encoding="utf-8") as f:
        added = f.read().splitlines()
    with open("/tmp/removed.txt", encoding="utf-8") as f:
        removed = f.read().splitlines()
    with open("configs.txt", encoding="utf-8") as f:
        all_lines = [l.strip() for l in f if l.strip()]
    total = len(all_lines)

    now = datetime.now(timezone.utc).strftime("%d %b %Y  •  %H:%M UTC")
    protocols, flags = get_stats(all_lines)

    # protocol line: "vless 28 · trojan 4"
    proto_str = " · ".join(f"{p} {c}" for p, c in protocols.most_common())
    # country line: "🇺🇸 26 · 🇳🇱 6"
    flag_str = " · ".join(f"{f} {c}" for f, c in flags.most_common(6))
    if len(flags) > 6:
        other = sum(c for _, c in flags.most_common()[6:])
        flag_str += f" · 🌐+{other}"

    if first_run:
        message = (
            f"🔔 <b>DGDreams Subscription</b>\n"
            f"<code>{now}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"✅ Active with <b>{total}</b> configs\n\n"
            f"📊 {proto_str}\n"
            f"🌍 {flag_str}\n\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🔗 <b>Subscription Link</b>\n"
            f"<code>{sub_url}</code>\n\n"
            f"<i>Copy the link above and import it in your VPN client.</i>"
        )
    else:
        net = len(added) - len(removed)
        net_str = f"+{net}" if net > 0 else str(net)
        net_emoji = "📈" if net > 0 else "📉" if net < 0 else "➡️"

        message = (
            f"🔔 <b>DGDreams Subscription</b>\n"
            f"<code>{now}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"📦 <b>{total}</b> configs  •  {net_emoji} <b>{net_str}</b>\n\n"
            f"📊 {proto_str}\n"
            f"🌍 {flag_str}\n\n"
        )

        if added:
            message += f"➕ {len(added)} added  "
        if removed:
            message += f"➖ {len(removed)} removed\n"
        if added or removed:
            message += "\n"

        message += (
            f"━━━━━━━━━━━━━━━━━━━━\n\n"
            f"🔗 <b>Subscription Link</b>\n"
            f"<code>{sub_url}</code>"
        )

    send_message(token, chat_id, message)
    print("Telegram notification sent successfully")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Send clean Telegram notification with subscription link.
"""

import html
import json
import os
import re
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

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


def subscription_block(sub_url: str, manifest_path: str) -> str:
    """Build the subscription-link section for Telegram."""
    links = [("All configs", sub_url)]
    path = Path(manifest_path)
    if path.is_file():
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
            links.extend(
                (item["name"], item["base64_url"])
                for item in manifest.get("repositories", [])
                if item.get("name") and item.get("base64_url")
            )
        except (OSError, json.JSONDecodeError, TypeError, KeyError):
            # The main notification should still be sent if an optional
            # generated manifest is unavailable or malformed.
            pass

    if len(links) == 1:
        return (
            "🔗 <b>Subscription Link</b>\n"
            f"<code>{html.escape(links[0][1])}</code>"
        )

    lines = ["🔗 <b>Subscription Links</b>"]
    for label, url in links:
        lines.append(f"• <b>{html.escape(label)}</b>\n<code>{html.escape(url)}</code>")
    return "\n".join(lines)


def main() -> None:
    token = os.environ.get("TG_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TG_CHAT_ID", "").strip()
    first_run = os.environ.get("FIRST_RUN", "no") == "yes"
    sub_url = os.environ.get("SUB_URL", SUB_BASE_URL + "/configs_base64.txt").strip()
    manifest_path = os.environ.get("REPOSITORY_MANIFEST", "/tmp/repositories/manifest.json")
    links_block = subscription_block(sub_url, manifest_path)

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
            f"{links_block}\n\n"
            f"<i>Copy any link above and import it in your VPN client.</i>"
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

        message += f"━━━━━━━━━━━━━━━━━━━━\n\n{links_block}"

    send_message(token, chat_id, message)
    print("Telegram notification sent successfully")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Send config diff notification to Telegram with clean formatting.
"""

import os
import re
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone

TG_API = "https://api.telegram.org/bot{token}/sendMessage"
CHUNK_SIZE = 3800
REQUEST_TIMEOUT = 20

PROTOCOL_RE = re.compile(r"^(vless|vmess|trojan|ss|hysteria2|tuic)://", re.IGNORECASE)
FLAG_RE = re.compile(r"#DGDreams\s+(.+)$")


def send_message(token: str, chat_id: str, text: str, parse_mode: str = "HTML") -> None:
    """Send a message to Telegram, splitting into chunks if needed."""
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
            TG_API.format(token=token),
            data=payload,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
            result = resp.read().decode("utf-8")
            if '"ok":true' not in result:
                raise RuntimeError(f"Telegram API error: {result}")


def parse_protocol(line: str) -> str:
    m = PROTOCOL_RE.match(line)
    return m.group(1).lower() if m else "unknown"


def parse_flag(line: str) -> str:
    m = FLAG_RE.search(line)
    return m.group(1).strip() if m else "🌐"


def make_bar(count: int, max_count: int, width: int = 10) -> str:
    """Make a simple text bar chart."""
    if max_count == 0:
        return ""
    filled = round(count / max_count * width)
    return "█" * filled + "░" * (width - filled)


def build_stats_block(configs: list[str]) -> str:
    """Build protocol and country stats block."""
    if not configs:
        return ""

    protocols = Counter(parse_protocol(c) for c in configs)
    flags = Counter(parse_flag(c) for c in configs)

    # protocol breakdown
    max_proto = max(protocols.values())
    proto_lines = []
    for proto, count in protocols.most_common():
        bar = make_bar(count, max_proto)
        proto_lines.append(f"  {proto:<10} {bar} {count}")

    # country breakdown (top 8)
    max_flag = max(flags.values())
    flag_lines = []
    for flag, count in flags.most_common(8):
        bar = make_bar(count, max_flag)
        flag_lines.append(f"  {flag:<4} {bar} {count}")

    if len(flags) > 8:
        other = sum(c for f, c in flags.most_common()[8:])
        flag_lines.append(f"  🌐 +{len(flags) - 8} more    {other}")

    lines = []
    lines.append("<b>📊 Protocol Breakdown</b>")
    lines.append("<pre>")
    lines.extend(proto_lines)
    lines.append("</pre>")
    lines.append("<b>🌍 Country Distribution</b>")
    lines.append("<pre>")
    lines.extend(flag_lines)
    lines.append("</pre>")

    return "\n".join(lines)


def format_config_line(line: str, idx: int) -> str:
    """Format a single config for display."""
    m = PROTOCOL_RE.match(line)
    proto = m.group(1).upper() if m else "???"
    flag = parse_flag(line)
    # extract host for display
    base = line.split("#", 1)[0]
    at_idx = base.find("@")
    if at_idx > 0:
        host_part = base[at_idx + 1 :]
        # trim to host:port
        colon = host_part.rfind(":")
        host_display = host_part[:colon] if colon > 0 else host_part
        # shorten IP
        host_display = host_display.replace("workers.dev", "workers")
    else:
        host_display = "unknown"
    return f"  {idx:>3}. {flag} {proto:<7} {host_display}"


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

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    if first_run:
        with open("configs.txt", encoding="utf-8") as f:
            all_configs = [l.strip() for l in f if l.strip()]

        message = (
            f"╔══════════════════════════╗\n"
            f"║  <b>DGDreams Sub Active</b>  ║\n"
            f"╚══════════════════════════╝\n\n"
            f"✅ Subscription initialized with <b>{total}</b> configs\n"
            f"🕐 {now}\n\n"
            f"{build_stats_block(all_configs)}\n\n"
            f"<i>Future updates will only show changes.</i>"
        )
    else:
        net = len(added) - len(removed)
        net_str = f"+{net}" if net > 0 else str(net)
        emoji = "📈" if net > 0 else "📉" if net < 0 else "➡️"

        message = (
            f"╔══════════════════════════╗\n"
            f"║  <b>DGDreams Sub Update</b>  ║\n"
            f"╚══════════════════════════╝\n\n"
            f"🕐 {now}\n\n"
            f"<b>📦 Summary</b>\n"
            f"  Total: <b>{total}</b> configs\n"
            f"  {emoji} Net: <b>{net_str}</b>\n\n"
        )

        if added or removed:
            message += f"<b>━━━ Changes ━━━</b>\n\n"

        if added:
            # show up to 10 added, then summary
            shown = added[:10]
            message += f"<b>➕ Added ({len(added)})</b>\n"
            message += "<pre>\n"
            for i, line in enumerate(shown, 1):
                message += format_config_line(line, i) + "\n"
            message += "</pre>\n"
            if len(added) > 10:
                message += f"<i>  ... and {len(added) - 10} more\n</i>"
            message += "\n"

        if removed:
            shown = removed[:10]
            message += f"<b>➖ Removed ({len(removed)})</b>\n"
            message += "<pre>\n"
            for i, line in enumerate(shown, 1):
                message += format_config_line(line, i) + "\n"
            message += "</pre>\n"
            if len(removed) > 10:
                message += f"<i>  ... and {len(removed) - 10} more\n</i>"
            message += "\n"

        if not added and not removed:
            message += "<i>No changes detected.</i>\n"

    send_message(token, chat_id, message)
    print("Telegram notification sent successfully")


if __name__ == "__main__":
    main()

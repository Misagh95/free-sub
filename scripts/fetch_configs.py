#!/usr/bin/env python3
"""
Fetch VPN configs from sources, detect plain/base64, decode and validate.
"""

import base64
import re
import sys
import urllib.request
from pathlib import Path

PROTOCOL_RE = re.compile(
    r"^(vless|vmess|trojan|ss|hysteria2|tuic)://",
    re.IGNORECASE,
)

USER_AGENT = "v2rayNG/1.9.16"
CONNECT_TIMEOUT = 20
MAX_TIMEOUT = 60


def fetch_url(url: str) -> bytes | None:
    """Fetch a URL with timeout and return raw bytes, or None on failure."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=MAX_TIMEOUT) as resp:
            return resp.read()
    except Exception as exc:
        print(f"  ✗ Failed: {exc}", file=sys.stderr)
        return None


def is_plain_configs(data: bytes) -> bool:
    """Check if raw bytes contain plain-text config lines."""
    try:
        text = data.decode("utf-8", errors="ignore")
    except Exception:
        return False
    return bool(PROTOCOL_RE.search(text))


def decode_base64(data: bytes) -> str:
    """Try to base64-decode raw bytes, return decoded text or empty string."""
    # strip whitespace
    raw = re.sub(r"\s+", "", data.decode("ascii", errors="ignore"))
    # pad
    raw += "=" * ((4 - len(raw) % 4) % 4)
    try:
        decoded = base64.b64decode(raw, validate=False)
        return decoded.decode("utf-8", errors="ignore")
    except Exception:
        return ""


def validate_line(line: str) -> bool:
    """Validate that a line is a well-formed config URL."""
    line = line.strip()
    if not line:
        return False
    if not PROTOCOL_RE.match(line):
        return False
    # basic structural check: must have @ and : after protocol
    base = line.split("#", 1)[0]
    if "@" not in base:
        return False
    return True


def main(sources_path: str = "sources.txt", output_path: str = "/tmp/raw_configs.txt"):
    if not Path(sources_path).is_file():
        print(f"ERROR: {sources_path} not found", file=sys.stderr)
        sys.exit(1)

    all_lines: list[str] = []

    for raw_url in Path(sources_path).read_text(encoding="utf-8").splitlines():
        url = raw_url.strip()
        if not url or url.startswith("#"):
            continue

        print(f"Fetching: {url[:80]}...")
        data = fetch_url(url)
        if data is None:
            continue

        if is_plain_configs(data):
            text = data.decode("utf-8", errors="ignore")
            lines = text.splitlines()
            valid = [l for l in lines if validate_line(l.strip())]
            print(f"  → plain text: {len(lines)} lines, {len(valid)} valid configs")
            all_lines.extend(valid)
            continue

        # try base64
        decoded = decode_base64(data)
        if decoded:
            lines = decoded.splitlines()
            valid = [l for l in lines if validate_line(l.strip())]
            print(f"  → base64 decoded: {len(lines)} lines, {len(valid)} valid configs")
            all_lines.extend(valid)
        else:
            print(f"  → base64 decode failed, skipping")

    # deduplicate
    unique = sorted({line.strip() for line in all_lines})

    print(f"\nTotal raw: {len(all_lines)}, unique: {len(unique)}")

    if not unique:
        print("ERROR: no valid configs were found", file=sys.stderr)
        sys.exit(1)

    Path(output_path).write_text("\n".join(unique) + "\n", encoding="utf-8")
    print(f"Written to {output_path}")


if __name__ == "__main__":
    sources = sys.argv[1] if len(sys.argv) > 1 else "sources.txt"
    output = sys.argv[2] if len(sys.argv) > 2 else "/tmp/raw_configs.txt"
    main(sources, output)

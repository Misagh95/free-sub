#!/usr/bin/env python3
"""
Rename configs with DGDreams branding and country flags.
Includes DNS cache, DNS timeout, and geo-lookup with retry/backoff.
"""

import base64
import json
import re
import socket
import time
import urllib.parse
import urllib.request
from pathlib import Path

PROTOCOL_RE = re.compile(
    r"^(vless|vmess|trojan|ss|hysteria2|tuic)://",
    re.IGNORECASE,
)

DNS_TIMEOUT = 5  # seconds
GEO_TIMEOUT = 8  # seconds
GEO_RETRIES = 2
GEO_BACKOFF = 1  # seconds

# caches
_dns_cache: dict[str, str | None] = {}
_geo_cache: dict[str, str] = {}

socket.setdefaulttimeout(DNS_TIMEOUT)


def country_flag(country_code: str) -> str:
    """Convert 2-letter country code to emoji flag."""
    cc = (country_code or "").upper()
    if len(cc) != 2 or not cc.isalpha():
        return "🌐"
    return "".join(chr(127397 + ord(c)) for c in cc)


def extract_host(line: str) -> str | None:
    """Extract hostname from a config URL."""
    base = line.split("#", 1)[0].strip()
    try:
        parsed = urllib.parse.urlsplit(base)
        if parsed.hostname:
            return parsed.hostname.strip("[]")
    except Exception:
        pass
    match = re.search(r"@([^:/?#]+)", base)
    return match.group(1) if match else None


def resolve_ip(host: str | None) -> str | None:
    """Resolve hostname to IP with caching."""
    if not host:
        return None
    if host in _dns_cache:
        return _dns_cache[host]
    # already an IP
    if re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}", host):
        _dns_cache[host] = host
        return host
    try:
        ip = socket.gethostbyname(host)
        _dns_cache[host] = ip
        return ip
    except Exception:
        _dns_cache[host] = None
        return None


def get_country_flag(ip: str | None) -> str:
    """Lookup country flag from IP with retry and backoff."""
    if not ip:
        return "🌐"
    if ip in _geo_cache:
        return _geo_cache[ip]

    for attempt in range(GEO_RETRIES + 1):
        try:
            req = urllib.request.Request(
                f"https://ipwho.is/{urllib.parse.quote(ip)}",
                headers={"User-Agent": "DGDreams-Config-Updater/1.0"},
            )
            with urllib.request.urlopen(req, timeout=GEO_TIMEOUT) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            result = country_flag(data.get("country_code", ""))
            _geo_cache[ip] = result
            return result
        except Exception:
            if attempt < GEO_RETRIES:
                time.sleep(GEO_BACKOFF * (attempt + 1))

    result = "🌐"
    _geo_cache[ip] = result
    return result


def rename_config(line: str) -> str | None:
    """Rename a single config line with DGDreams brand and flag."""
    line = line.strip()
    if not PROTOCOL_RE.match(line):
        return None
    base = line.split("#", 1)[0].strip()
    host = extract_host(base)
    ip = resolve_ip(host)
    flag = get_country_flag(ip)
    return f"{base}#DGDreams {flag}"


def main(
    raw_path: str = "/tmp/raw_configs.txt",
    out_txt: str = "configs.txt",
    out_b64: str = "configs_base64.txt",
):
    raw_text = Path(raw_path).read_text(encoding="utf-8", errors="ignore")

    configs: set[str] = set()
    for line in raw_text.splitlines():
        renamed = rename_config(line)
        if renamed:
            configs.add(renamed)

    configs_sorted = sorted(configs)
    output = ("\n".join(configs_sorted) + "\n") if configs_sorted else ""

    Path(out_txt).write_text(output, encoding="utf-8")
    Path(out_b64).write_text(
        base64.b64encode(output.encode("utf-8")).decode("ascii"),
        encoding="utf-8",
    )
    print(f"Final configs: {len(configs_sorted)}")


if __name__ == "__main__":
    import sys

    raw = sys.argv[1] if len(sys.argv) > 1 else "/tmp/raw_configs.txt"
    txt = sys.argv[2] if len(sys.argv) > 2 else "configs.txt"
    b64 = sys.argv[3] if len(sys.argv) > 3 else "configs_base64.txt"
    main(raw, txt, b64)

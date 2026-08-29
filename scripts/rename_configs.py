#!/usr/bin/env python3
"""
Rename configs with unique random names based on country.
Includes DNS cache, DNS timeout, and geo-lookup with retry/backoff.
"""

import base64
import json
import random
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

DNS_TIMEOUT = 5
GEO_TIMEOUT = 8
GEO_RETRIES = 2
GEO_BACKOFF = 1

_dns_cache: dict[str, str | None] = {}
_geo_cache: dict[str, tuple[str, str]] = {}  # ip -> (country_code, flag)

socket.setdefaulttimeout(DNS_TIMEOUT)

# Country code → random name components
COUNTRY_NAMES = {
    "US": ["Liberty", "Eagle", "Nova", "Atlas", "Prime", "Apex", "Titan", "Blaze"],
    "NL": ["Amsterdam", "Tulip", "Delta", "Breeze", "Harbor", "Windmill", "Dike", "Polder"],
    "DE": ["Berlin", "Munich", "Eagle", "Iron", "Rex", "Sturm", "Kraft", "Falk"],
    "FR": ["Paris", "Lyon", "Eiffel", "Rouge", "Lumière", "Azur", "Bleu", "Ciel"],
    "GB": ["London", "Crown", "Thames", "Royal", "Shield", "Brit", "Sterling", "Albion"],
    "JP": ["Sakura", "Dragon", "Zen", "Rising", "Kaze", "Kumo", "Tsuki", "Shiro"],
    "SG": ["Lion", "Bay", "Orchid", "Pearl", "Garden", "Tropica", "Zenith", "Coral"],
    "HK": ["Harbor", "Peak", "Star", "Jade", "Dragon", "Neon", "Metro", "Spark"],
    "CA": ["Maple", "North", "Polar", "Bear", "Snow", "Frost", "Arctic", "Glacier"],
    "AU": ["Kangaroo", "Reef", "Outback", "Koala", "Sun", "Wave", "Reef", "Coral"],
    "IN": ["Tiger", "Lotus", "Delhi", "Mumbai", "Spice", "Gold", "Saffron", "Indus"],
    "BR": ["Amazon", "Rio", "Carnival", "Tropical", "Samba", "Copa", "Verde", "Sol"],
    "KR": ["Seoul", "K-Star", "Han", "Neo", "Cyber", "Pulse", "Wave", "Core"],
    "IT": ["Roma", "Milan", "Venus", "Olive", "Colosseo", "Azzurro", "Luna", "Sole"],
    "ES": ["Madrid", "Flamenco", "Sol", "Torero", "Iberia", "Cobre", "Costa", "Mar"],
    "SE": ["Stockholm", "Viking", "Fjord", "Aurora", "Nordic", "Frost", "Elk", "Saga"],
    "NO": ["Oslo", "Fjord", "Viking", "Aurora", "Nordic", "Storm", "Glacier", "Bjorn"],
    "FI": ["Helsinki", "Sauna", "Snow", "Fox", "Frost", "Birch", "Lumi", "Suomi"],
    "PL": ["Warsaw", "Krakow", "Bison", "Amber", "Vistula", "Pioneer", "Forge", "Shield"],
    "TR": ["Istanbul", "Bosphorus", "Crescent", "Anatolia", "Sultan", "Spice", "Silk", "Odin"],
    "AE": ["Dubai", "Oasis", "Falcon", "Sand", "Gold", "Pearl", "Desert", "Sahara"],
    "ZA": ["Cape", "Diamond", "Safari", "Lion", "Ubuntu", "Thorn", "Kruger", "Sun"],
    "MX": ["Aztec", "Maya", "Cactus", "Tequila", "Sierra", "Sol", "Luna", "Jaguar"],
    "CH": ["Alps", "Bern", "Glacier", "Summit", "Crystal", "Peak", "Snow", "Yodel"],
}

DEFAULT_NAMES = ["Cloud", "Node", "Relay", "Bridge", "Proxy", "Core", "Edge", "Beacon"]

# Used numbers per country to avoid duplicates
_used_numbers: dict[str, set[int]] = {}


def country_flag(country_code: str) -> str:
    cc = (country_code or "").upper()
    if len(cc) != 2 or not cc.isalpha():
        return "🌐"
    return "".join(chr(127397 + ord(c)) for c in cc)


def generate_name(country_code: str) -> str:
    """Generate a unique random name for a config based on its country."""
    cc = (country_code or "").upper()
    if cc not in _used_numbers:
        _used_numbers[cc] = set()

    names = COUNTRY_NAMES.get(cc, DEFAULT_NAMES)
    base = random.choice(names)

    # find unused number
    for _ in range(100):
        num = random.randint(1, 999)
        if num not in _used_numbers[cc]:
            _used_numbers[cc].add(num)
            return f"{base}-{num}"

    # fallback: use timestamp
    num = int(time.time() * 1000) % 10000
    return f"{base}-{num}"


def extract_host(line: str) -> str | None:
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
    if not host:
        return None
    if host in _dns_cache:
        return _dns_cache[host]
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


def get_country_info(ip: str | None) -> tuple[str, str]:
    """Return (country_code, flag) for an IP."""
    if not ip:
        return ("", "🌐")
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
            cc = (data.get("country_code") or "").upper()
            flag = country_flag(cc)
            _geo_cache[ip] = (cc, flag)
            return (cc, flag)
        except Exception:
            if attempt < GEO_RETRIES:
                time.sleep(GEO_BACKOFF * (attempt + 1))

    _geo_cache[ip] = ("", "🌐")
    return ("", "🌐")


def rename_config(line: str) -> str | None:
    """Rename a config with a unique random country-based name."""
    line = line.strip()
    if not PROTOCOL_RE.match(line):
        return None

    base = line.split("#", 1)[0].strip()
    host = extract_host(base)
    ip = resolve_ip(host)
    cc, flag = get_country_info(ip)
    name = generate_name(cc)

    return f"{base}#{flag} {name}"


def main(
    raw_path: str = "/tmp/raw_configs.txt",
    out_txt: str = "configs.txt",
    out_b64: str = "configs_base64.txt",
):
    random.seed()  # use system entropy

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

    # print sample names
    for c in configs_sorted[:5]:
        name = c.split("#", 1)[1] if "#" in c else c
        print(f"  {name}")


if __name__ == "__main__":
    import sys

    raw = sys.argv[1] if len(sys.argv) > 1 else "/tmp/raw_configs.txt"
    txt = sys.argv[2] if len(sys.argv) > 2 else "configs.txt"
    b64 = sys.argv[3] if len(sys.argv) > 3 else "configs_base64.txt"
    main(raw, txt, b64)

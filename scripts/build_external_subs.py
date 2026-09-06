#!/usr/bin/env python3
"""
Publish each external source as its own individual subscription.

Reads ``external_sources.txt`` (``label<TAB>url`` per line, ``#`` for
comments) and writes ``<label>.txt`` (plain text, deduplicated) plus
``<label>_base64.txt`` (Base64-encoded for subscription clients) into the
output directory. A JSON manifest is written for the Telegram notifier so
every generated sub-link can be announced automatically.

A source that fails or returns no valid configs keeps its previous output
files untouched, so a temporary outage never wipes out a working subscription.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_configs import extract_config_lines, fetch_url, validate_line  # noqa: E402


def parse_sources(path: Path) -> list[tuple[str, str]]:
    """Return (label, url) pairs from the external sources file."""
    sources: list[tuple[str, str]] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "\t" in line:
            label, url = line.split("\t", 1)
        elif "|" in line:
            label, url = line.split("|", 1)
        else:
            print(f"  ✗ Skipping malformed line: {line}", file=sys.stderr)
            continue
        label = label.strip()
        url = url.strip()
        if label and url:
            sources.append((label, url))
    return sources


def fetch_subscription(url: str) -> list[str]:
    """Fetch a source and return validated, deduplicated config lines."""
    data = fetch_url(url)
    if data is None:
        return []

    try:
        _, decoded_lines = extract_config_lines(data)
    except Exception as exc:
        print(f"  ✗ Decode error: {exc}", file=sys.stderr)
        return []

    return sorted({line.strip() for line in decoded_lines if validate_line(line.strip())})


def main(
    sources_path: str = "external_sources.txt",
    output_dir: str = ".",
    base_url: str = "https://raw.githubusercontent.com/Misagh95/free-sub/main",
    manifest_path: str = "/tmp/external_subs.json",
) -> None:
    sources = parse_sources(Path(sources_path))
    if not sources:
        print("ERROR: no external sources found", file=sys.stderr)
        sys.exit(1)

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    manifest: dict = {"version": 1, "subscriptions": []}
    failures = 0

    for label, url in sources:
        print(f"Fetching {label}: {url[:80]}...")
        configs = fetch_subscription(url)

        if not configs:
            print(
                f"  ⚠ {label}: no valid configs; keeping previous subscription",
                file=sys.stderr,
            )
            failures += 1
            config_count = (
                len(Path(out / f"{label}.txt").read_text(encoding="utf-8", errors="ignore").splitlines())
                if Path(out / f"{label}.txt").is_file()
                else 0
            )
            manifest["subscriptions"].append(
                {
                    "label": label,
                    "config_count": config_count,
                    "plain_url": f"{base_url}/{label}.txt",
                    "base64_url": f"{base_url}/{label}_base64.txt",
                }
            )
            continue

        output = "\n".join(configs) + "\n"
        Path(out / f"{label}.txt").write_text(output, encoding="utf-8")
        Path(out / f"{label}_base64.txt").write_text(
            base64.b64encode(output.encode("utf-8")).decode("ascii"),
            encoding="ascii",
        )
        print(f"  → {label}: {len(configs)} configs")
        manifest["subscriptions"].append(
            {
                "label": label,
                "config_count": len(configs),
                "plain_url": f"{base_url}/{label}.txt",
                "base64_url": f"{base_url}/{label}_base64.txt",
            }
        )

    if failures == len(sources):
        print("ERROR: all external sources failed", file=sys.stderr)
        sys.exit(1)

    Path(manifest_path).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Manifest written to {manifest_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "sources",
        nargs="?",
        default="external_sources.txt",
        help="external sources file (default: external_sources.txt)",
    )
    parser.add_argument(
        "output",
        nargs="?",
        default=".",
        help="output directory for generated subscriptions (default: current dir)",
    )
    parser.add_argument(
        "--base-url",
        default=os.environ.get(
            "EXTERNAL_SUB_BASE_URL",
            "https://raw.githubusercontent.com/Misagh95/free-sub/main",
        ),
        help="base URL used for the generated sub-links",
    )
    parser.add_argument(
        "--manifest",
        default=os.environ.get("EXTERNAL_SUBS_MANIFEST", "/tmp/external_subs.json"),
        help="path for the generated JSON manifest",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    main(args.sources, args.output, args.base_url, args.manifest)
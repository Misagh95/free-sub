#!/usr/bin/env python3
"""
Build deterministic subscription shards for publishing to multiple repositories.

The main repository keeps the complete ``configs.txt`` subscription.  This
script creates smaller, independently usable subscriptions for repositories
named ``<prefix>-01``, ``<prefix>-02``, ... .  A SHA-256 bucket assignment is
used instead of slicing the sorted list, so a small change does not move every
config to a different repository.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import os
import re
import shutil
from pathlib import Path

PROTOCOL_RE = re.compile(r"^(vless|vmess|trojan|ss|hysteria2|tuic)://", re.IGNORECASE)
DEFAULT_MAX_CONFIGS = 500
MIN_REPOSITORIES = 2


def read_configs(path: Path) -> list[str]:
    """Read, validate, and deduplicate config URLs from *path*."""
    configs = {
        line.strip()
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines()
        if line.strip() and PROTOCOL_RE.match(line.strip())
    }
    return sorted(configs)


def repository_count(total: int, max_configs: int) -> int:
    """Return an automatic repository count while preserving the plural form."""
    if total == 0:
        return 0
    # There cannot be more non-empty repositories than configs.  A one-config
    # input therefore remains a single repository; normal subscriptions use
    # at least two shards.
    return min(total, max(MIN_REPOSITORIES, math.ceil(total / max_configs)))


def bucket_for(config: str, count: int) -> int:
    """Return a stable bucket number for a config URL."""
    digest = hashlib.sha256(config.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], byteorder="big") % count


def make_buckets(configs: list[str], count: int) -> list[list[str]]:
    """Assign configs to stable buckets and ensure no bucket is empty."""
    buckets = [[] for _ in range(count)]
    for config in configs:
        buckets[bucket_for(config, count)].append(config)

    # An empty bucket is unlikely with the current subscription size, but
    # moving one item from the largest bucket makes the output safe for small
    # test subscriptions too.  This branch is deterministic.
    for index, bucket in enumerate(buckets):
        if bucket:
            continue
        donor_index = max(range(count), key=lambda i: (len(buckets[i]), -i))
        if len(buckets[donor_index]) <= 1:
            raise ValueError("cannot create non-empty repositories from the input")
        moved = buckets[donor_index].pop()
        bucket.append(moved)

    for bucket in buckets:
        bucket.sort()
    return buckets


def repository_name(prefix: str, index: int, count: int) -> str:
    """Build a zero-padded repository name."""
    width = max(2, len(str(count)))
    return f"{prefix}-{index + 1:0{width}d}"


def write_subscription(directory: Path, configs: list[str], name: str, owner: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    output = ("\n".join(configs) + "\n") if configs else ""
    directory.joinpath("configs.txt").write_text(output, encoding="utf-8")
    directory.joinpath("configs_base64.txt").write_text(
        base64.b64encode(output.encode("utf-8")).decode("ascii"),
        encoding="ascii",
    )

    raw_base = f"https://raw.githubusercontent.com/{owner}/{name}/main"
    readme = f"""# {name}

Automatically generated subscription shard from [`{owner}/free-sub`](https://github.com/{owner}/free-sub).

- Plain text: `{raw_base}/configs.txt`
- Base64 subscription: `{raw_base}/configs_base64.txt`
- Configurations in this shard: **{len(configs)}**

This repository is managed by the updater workflow. Changes may be overwritten
on the next update.
"""
    directory.joinpath("README.md").write_text(readme, encoding="utf-8")


def build(
    input_path: Path,
    output_root: Path,
    prefix: str,
    owner: str,
    max_configs: int,
) -> dict:
    if max_configs < 1:
        raise ValueError("max_configs must be at least 1")
    if not prefix or "/" in prefix or " " in prefix:
        raise ValueError("prefix must be a non-empty repository name fragment")
    if not owner or "/" in owner:
        raise ValueError("owner must be a GitHub account or organization name")

    configs = read_configs(input_path)
    count = repository_count(len(configs), max_configs)

    output_root.mkdir(parents=True, exist_ok=True)
    # Only remove directories belonging to this generated prefix.  This keeps
    # an accidentally shared output directory from being wiped wholesale.
    for child in output_root.iterdir():
        if child.is_dir() and child.name.startswith(f"{prefix}-"):
            shutil.rmtree(child)
        elif child.name in {"manifest.json", "published-manifest.json"}:
            child.unlink()

    repositories: list[dict] = []
    if count:
        buckets = make_buckets(configs, count)
        for index, bucket in enumerate(buckets):
            name = repository_name(prefix, index, count)
            write_subscription(output_root / name, bucket, name, owner)
            raw_base = f"https://raw.githubusercontent.com/{owner}/{name}/main"
            repositories.append(
                {
                    "name": name,
                    "path": name,
                    "config_count": len(bucket),
                    "plain_url": f"{raw_base}/configs.txt",
                    "base64_url": f"{raw_base}/configs_base64.txt",
                }
            )

    manifest = {
        "version": 1,
        "source": str(input_path),
        "total_configs": len(configs),
        "max_configs_per_repository": max_configs,
        "repositories": repositories,
    }
    output_root.joinpath("manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return manifest


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="canonical configs.txt file")
    parser.add_argument("output", type=Path, help="directory for generated repositories")
    parser.add_argument(
        "--prefix",
        default=os.environ.get("REPOSITORY_PREFIX", "free-sub"),
        help="repository name prefix (default: free-sub)",
    )
    parser.add_argument(
        "--owner",
        default=os.environ.get("REPOSITORY_OWNER", os.environ.get("GITHUB_REPOSITORY_OWNER", "Misagh95")),
        help="GitHub owner used in generated links",
    )
    parser.add_argument(
        "--max-configs-per-repository",
        type=int,
        default=int(os.environ.get("MAX_CONFIGS_PER_REPOSITORY", DEFAULT_MAX_CONFIGS)),
        help=f"automatic shard size (default: {DEFAULT_MAX_CONFIGS})",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manifest = build(
        input_path=args.input,
        output_root=args.output,
        prefix=args.prefix,
        owner=args.owner,
        max_configs=args.max_configs_per_repository,
    )
    print(
        f"Built {len(manifest['repositories'])} repositories "
        f"for {manifest['total_configs']} configs"
    )
    for repository in manifest["repositories"]:
        print(f"  {repository['name']}: {repository['config_count']} configs")


if __name__ == "__main__":
    main()

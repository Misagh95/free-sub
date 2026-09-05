#!/usr/bin/env python3
"""
Create/update the generated subscription repositories with GitHub CLI.

The workflow supplies GH_TOKEN through the MULTI_REPO_TOKEN secret.  The
publisher deliberately manages only the generated subscription files and
leaves any other files in an existing repository untouched.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

MANAGED_FILES = ("configs.txt", "configs_base64.txt", "README.md")


def run(
    command: list[str],
    *,
    cwd: Path | None = None,
    check: bool = True,
    quiet: bool = False,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        check=check,
        text=True,
        stdout=subprocess.DEVNULL if quiet else None,
        stderr=subprocess.PIPE if quiet else None,
    )


def repository_exists(full_name: str) -> bool:
    result = run(["gh", "repo", "view", full_name], check=False, quiet=True)
    return result.returncode == 0


def create_repository(full_name: str) -> None:
    print(f"Creating {full_name}")
    run(
        [
            "gh",
            "repo",
            "create",
            full_name,
            "--public",
            "--description",
            "Automatically generated free-sub subscription shard",
        ]
    )


def prepare_checkout(directory: Path, full_name: str) -> None:
    """Clone an existing repo or initialize a new main branch."""
    if repository_exists(full_name):
        run(["git", "clone", "--depth", "1", f"https://github.com/{full_name}.git", str(directory)])
        # Empty repositories clone successfully but have no branch/HEAD.
        if not (directory / ".git").exists():
            raise RuntimeError(f"clone did not create a Git checkout for {full_name}")
        result = run(["git", "rev-parse", "--verify", "HEAD"], cwd=directory, check=False, quiet=True)
        if result.returncode != 0:
            run(["git", "checkout", "-b", "main"], cwd=directory)
    else:
        directory.mkdir(parents=True, exist_ok=True)
        run(["git", "init", "-b", "main"], cwd=directory)
        run(
            ["git", "remote", "add", "origin", f"https://github.com/{full_name}.git"],
            cwd=directory,
        )


def sync_repository(source: Path, owner: str, repository: dict, workspace: Path) -> bool:
    name = repository["name"]
    full_name = f"{owner}/{name}"
    checkout = workspace / name
    if repository_exists(full_name):
        print(f"Updating {full_name}")
    else:
        create_repository(full_name)

    prepare_checkout(checkout, full_name)
    for filename in MANAGED_FILES:
        source_file = source / filename
        if not source_file.is_file():
            raise FileNotFoundError(f"missing generated file: {source_file}")
        shutil.copy2(source_file, checkout / filename)

    run(["git", "config", "user.name", "github-actions[bot]"], cwd=checkout)
    run(
        [
            "git",
            "config",
            "user.email",
            "41898282+github-actions[bot]@users.noreply.github.com",
        ],
        cwd=checkout,
    )
    # Force-add managed outputs in case an existing repository has a broad
    # ignore rule such as ``*.txt``.
    run(["git", "add", "-f", *MANAGED_FILES], cwd=checkout)
    changed = run(["git", "diff", "--cached", "--quiet"], cwd=checkout, check=False).returncode != 0
    if not changed:
        print(f"  {name}: unchanged")
        return False

    run(["git", "commit", "-m", "🔄 auto update configs"], cwd=checkout)
    run(["git", "push", "origin", "HEAD:main"], cwd=checkout)
    print(f"  {name}: published {repository['config_count']} configs")
    return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("generated", type=Path, help="directory produced by split_repositories.py")
    parser.add_argument(
        "--owner",
        default=os.environ.get("REPOSITORY_OWNER", os.environ.get("GITHUB_REPOSITORY_OWNER", "Misagh95")),
        help="GitHub account or organization that owns the output repositories",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        help="manifest path (default: GENERATED/manifest.json)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not os.environ.get("GH_TOKEN"):
        print("MULTI_REPO_TOKEN is not set; skipping repository publication")
        return
    if not args.owner or "/" in args.owner:
        raise SystemExit("owner must be a GitHub account or organization name")

    manifest_path = args.manifest or args.generated / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    repositories = manifest.get("repositories", [])
    if not repositories:
        print("No repositories to publish")
        return

    # Configure git's credential helper through gh so tokens never appear in
    # a remote URL or in command output.
    run(["gh", "auth", "setup-git"])
    with tempfile.TemporaryDirectory(prefix="free-sub-publish-") as temporary:
        workspace = Path(temporary)
        for repository in repositories:
            source = args.generated / repository["path"]
            sync_repository(source, args.owner, repository, workspace)

    # The notifier reads this marker rather than the build manifest.  That
    # prevents links to repositories that were not published when the token is
    # missing or a publication fails halfway through.
    published_manifest = args.generated / "published-manifest.json"
    shutil.copy2(manifest_path, published_manifest)
    print(f"Wrote publication manifest: {published_manifest}")


if __name__ == "__main__":
    main()

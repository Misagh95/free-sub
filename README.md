# Free Sub - Auto Update VPN Configs

Automatic subscription updater that fetches VPN configs from multiple Cloudflare Workers sources, deduplicates them, and renames every config with a deterministic female name specific to its server's country, prefixed with that country's flag. The Cloudflare Workers sources are merged into **one combined subscription**, while each external GitHub source is published as its **own individual subscription**. The complete subscription remains in this repository, while smaller shards can be published to several GitHub repositories automatically.

## Subscription Links

| # | Link | Description |
|---|------|-------------|
| 1 | `https://raw.githubusercontent.com/Misagh95/free-sub/main/configs_base64.txt` | **Combined** subscription (all sources) |
| 2 | `https://raw.githubusercontent.com/Misagh95/free-sub/main/GLD1_base64.txt` | GLD1 |
| 3 | `https://raw.githubusercontent.com/Misagh95/free-sub/main/GLD2_base64.txt` | GLD2 |
| 4 | `https://raw.githubusercontent.com/Misagh95/free-sub/main/GLD3_base64.txt` | GLD3 |
| 5 | `https://raw.githubusercontent.com/Misagh95/free-sub/main/GLD4_base64.txt` | GLD4 |
| 6 | `https://raw.githubusercontent.com/Misagh95/free-sub/main/GLD5_base64.txt` | GLD5 |

Plain-text versions use the same filename without `_base64` (e.g. `configs.txt`, `GLD1.txt`). Copy any link above into your VPN client.

## How It Works

1. **Fetch** — Reads source URLs from `sources.txt`, downloads configs (plain-text, Base64, or Xray JSON)
2. **Rename** — Resolves each server's IP, looks up its country, and appends a deterministic female name specific to that country, like `#🇺🇸 Emma-569` to every config
3. **Deduplicate** — Removes duplicate configs and sorts them
4. **External subscriptions** — Fetches each URL from `external_sources.txt` separately, renames its configs the same way, and publishes it as its own `<label>.txt` / `<label>_base64.txt`
5. **Shard** — Splits the complete subscription into deterministic, smaller repository shards
6. **Commit & Push** — Auto-commits changes to all subscription files
7. **Publish** — Creates or updates `free-sub-01`, `free-sub-02`, ... repositories
8. **Notify** — Sends a summary of added/removed configs and all subscription links to Telegram

## Files

| File | Description |
|------|-------------|
| `sources.txt` | Cloudflare Workers source URLs (merged into the combined subscription; one per line, `#` for comments) |
| `external_sources.txt` | External sources published as individual subscriptions (`label<TAB>url`, one per line, `#` for comments) |
| `configs.txt` | Combined plain-text output — one config per line |
| `configs_base64.txt` | Base64-encoded combined subscription for subscription clients |
| `<label>.txt` / `<label>_base64.txt` | Plain / Base64 output for each external source |
| `scripts/fetch_configs.py` | Fetches and decodes configs from sources |
| `scripts/rename_configs.py` | Renames configs with deterministic female names and country flags |
| `scripts/build_external_subs.py` | Builds the individual external subscriptions |
| `scripts/split_repositories.py` | Builds deterministic multi-repository subscription shards |
| `scripts/publish_repositories.py` | Creates/updates the generated GitHub repositories |
| `scripts/notify_telegram.py` | Sends Telegram notifications with all subscription links |

## Setup

1. **Fork** this repository
2. Add these **GitHub Secrets**:
   - `SUB_TOKEN` — Subscription token (replaces `__TOKEN__` in `sources.txt`)
   - `TG_BOT_TOKEN` — Telegram bot token for notifications
   - `TG_CHAT_ID` — Telegram chat ID for notifications
   - `MULTI_REPO_TOKEN` — GitHub token with permission to create and push to repositories owned by the account (a classic token with `repo` scope is the simplest option). This is required for the generated shards; without it, the main subscription still updates normally.
3. The workflow runs every 6 hours automatically, or trigger manually from the **Actions** tab (run it once right after setup to generate the first subscription files)

## Multi-repository output

The workflow automatically chooses the number of repositories using a limit of 500 configs per repository, with at least two repositories. For the current subscription this produces names such as `Misagh95/free-sub-01` and `Misagh95/free-sub-02`. Each generated repository contains both `configs.txt` and `configs_base64.txt` and can be imported independently.

Configs are assigned with a SHA-256 bucket, not by list position, so a normal update does not reshuffle the entire subscription. The generated repositories are intentionally managed outputs; files other than the generated README and subscription files are left untouched.

## Supported Protocols

`vless://` · `vmess://` · `trojan://` · `ss://` · `hysteria2://` · `tuic://`

## License

Public — use freely.
# Free Sub - Auto Update VPN Configs

Automatic subscription updater that fetches VPN configs from multiple Cloudflare Workers sources, deduplicates and renames them with DGDreams branding, and publishes updates. The complete subscription remains in this repository, while smaller shards can be published to several GitHub repositories automatically.

## How It Works

1. **Fetch** — Reads source URLs from `sources.txt`, downloads configs (plain-text or Base64-encoded)
2. **Rename** — Resolves each server's IP, looks up its country, and appends `#DGDreams 🏳️` to every config
3. **Deduplicate** — Removes duplicate configs and sorts them
4. **Shard** — Splits the complete subscription into deterministic, smaller repository shards
5. **Commit & Push** — Auto-commits changes to `configs.txt` and `configs_base64.txt`
6. **Publish** — Creates or updates `free-sub-01`, `free-sub-02`, ... repositories
7. **Notify** — Sends a summary of added/removed configs and all subscription links to Telegram

## Files

| File | Description |
|------|-------------|
| `sources.txt` | List of source URLs (one per line, `#` for comments) |
| `configs.txt` | Plain-text output — one config per line |
| `configs_base64.txt` | Base64-encoded version of `configs.txt` for subscription clients |
| `scripts/fetch_configs.py` | Fetches and decodes configs from sources |
| `scripts/rename_configs.py` | Renames configs with DGDreams branding and country flags |
| `scripts/split_repositories.py` | Builds deterministic multi-repository subscription shards |
| `scripts/publish_repositories.py` | Creates/updates the generated GitHub repositories |
| `scripts/notify_telegram.py` | Sends Telegram notifications with all subscription links |

## Setup

1. **Fork** this repository
2. Add these **GitHub Secrets**:
   - `SUB_TOKEN` — Subscription token (replaces `__TOKEN__` in `sources.txt`)
   - `TG_BOT_TOKEN` — Telegram bot token for notifications
   - `TG_CHAT_ID` — Telegram chat ID for notifications
   - `MULTI_REPO_TOKEN` — GitHub token with permission to create and push to repositories owned by the account. This is required for the generated shards; without it, the main subscription still updates normally.
3. The workflow runs every 6 hours automatically, or trigger manually from the **Actions** tab

## Multi-repository output

The workflow automatically chooses the number of repositories using a limit of 500 configs per repository, with at least two repositories. For the current subscription this produces names such as `Misagh95/free-sub-01` and `Misagh95/free-sub-02`. Each generated repository contains both `configs.txt` and `configs_base64.txt` and can be imported independently.

Configs are assigned with a SHA-256 bucket, not by list position, so a normal update does not reshuffle the entire subscription. The generated repositories are intentionally managed outputs; files other than the generated README and subscription files are left untouched.

## Supported Protocols

`vless://` · `vmess://` · `trojan://` · `ss://` · `hysteria2://` · `tuic://`

## License

Public — use freely.

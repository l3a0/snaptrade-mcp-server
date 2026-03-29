# CLAUDE.md — Context for AI assistants

This file is read automatically by Claude Code. It captures architecture decisions,
conventions, and gotchas that are not obvious from reading the code alone.

## What this project is

A read-only MCP (Model Context Protocol) server that exposes brokerage data from
SnapTrade to AI clients (Claude, Cursor, Windsurf, etc.). Users connect their
brokerage accounts via SnapTrade's OAuth flow, then AI tools can query balances,
positions, orders, and transactions — but cannot trade or modify accounts.

## Credential architecture

Two separate layers of credentials:

1. **App credentials** (SNAPTRADE_CLIENT_ID, SNAPTRADE_CONSUMER_KEY) — set as env
   vars in ~/.zshrc. Identify the MCP server application to SnapTrade.

2. **User credentials** (user_id, user_secret) — stored in ~/.snaptrade/config.json
   after running snaptrade_setup. Identify the specific brokerage user. The file is
   chmod 600 (owner read/write only).

`_get_client()` reads app credentials from env vars.
`_get_user()` reads user credentials from ~/.snaptrade/config.json only — it does
not fall back to env vars. The integration test fixture bootstraps config.json from
env vars if it doesn't exist (for CI runners).

## Security notes

- All tools are read-only. No trading, no account modification.
- Portfolio data flows through: SnapTrade API → this server → AI client.
- See the module docstring in server.py for data privacy policies per provider.
- No audit logging exists — this is a known gap documented in server.py.
- chmod 600 on config.json limits OS-level access but is not encryption.
- Do not use inline command-line credential assignments (visible in `ps aux`).

## MCP primitives used

- **Tools** — all dynamic operations (balances, positions, orders, etc.)
- **Resources** — kept for learning purposes but are not good resources (their data
  is dynamic, not static/cacheable). See the Resources section comment in server.py.
- **Prompt templates** — two templates for common query patterns.

## Testing

Integration tests require real credentials against a paper trading account (e.g.
Alpaca paper via SnapTrade). Never use real funded account credentials in tests.

- Local: fill in tests/integration/.env (gitignored)
- CI: set GitHub Actions Secrets; fixture bootstraps config.json automatically
- Run: `python -m pytest tests/integration/ -v`

## CI (GitHub Actions)

Defined in .github/workflows/ci.yml. Runs on every PR and push to main:
lint (ruff) → type check (pyright) → build check → import smoke test → integration tests.

Secrets are not passed to workflows from forked PRs (GitHub default), preventing
credential theft via malicious PRs.

## Dev setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

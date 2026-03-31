# SnapTrade MCP Server

[![CI](https://github.com/l3a0/snaptrade-mcp-server/actions/workflows/ci.yml/badge.svg)](https://github.com/l3a0/snaptrade-mcp-server/actions/workflows/ci.yml)

A read-only MCP (Model Context Protocol) server that connects AI agents to brokerage data via SnapTrade. Works with Claude Code, Claude Desktop, Cursor, Windsurf, and any MCP-compatible client.

**10 tools. Read-only. No trading. Safe by design.**

## What You Can Do

| Tool | Description |
| ---- | ----------- |
| `snaptrade_list_accounts` | List all connected brokerage accounts |
| `snaptrade_get_balance` | Cash balances for an account |
| `snaptrade_get_positions` | Current holdings (stocks, ETFs) |
| `snaptrade_get_orders` | Order history with filters |
| `snaptrade_get_activities` | Transaction log (dividends, fees) |
| `snaptrade_portfolio_summary` | All accounts + balances + positions in one call |
| `snaptrade_search_symbols` | Look up stocks/ETFs by name or ticker |
| `snaptrade_list_brokerages` | Supported brokerages |
| `snaptrade_check_status` | API health check |
| `snaptrade_setup` | Generate URL to connect a new brokerage |

## Prerequisites

1. **SnapTrade API credentials** — a `clientId` and `consumerKey` from [snaptrade.com](https://snaptrade.com). Sign up for a developer account and find your keys in the dashboard.
2. **Python 3.10+**

## Where do my API keys go?

Your SnapTrade credentials never leave your machine. Here's what happens:

- Your `clientId` and `consumerKey` are stored in a **local config file** on your computer (or in environment variables you set yourself).
- The MCP server reads them at startup to authenticate with SnapTrade's API.
- They are **never** sent to your AI client, **never** included in tool responses, and **never** logged.
- The server is read-only — it cannot trade, modify accounts, or delete anything.

This is the same way any API integration handles credentials. Your keys stay on your machine, period.

## Installation

### Option A: pip (recommended)

```bash
pip install snaptrade-mcp
```

This installs the `snaptrade-mcp` command and all dependencies.

### Option B: uvx (no install needed)

If you have [uv](https://docs.astral.sh/uv/) installed, you can run the server directly without installing anything:

```bash
uvx snaptrade-mcp
```

This downloads and runs it in an isolated environment automatically.

### Option C: Install from source

```bash
git clone https://github.com/l3a0/snaptrade-mcp-server.git
cd snaptrade-mcp-server
pip install .
```

## Add the MCP server to your AI client

### Claude Code

The `-s user` flag stores your credentials in your personal Claude config (`~/.claude/`), not in the project — so they never end up in git.

```bash
claude mcp add snaptrade -s user \
  -e SNAPTRADE_CLIENT_ID=your_client_id \
  -e SNAPTRADE_CONSUMER_KEY=your_consumer_key \
  -- snaptrade-mcp
```

Then restart Claude Code and run `/mcp` to verify the server appears with all 10 tools.

**Alternative:** If you prefer to set credentials as environment variables in your shell (add to `~/.zshrc` or `~/.bashrc`), you can skip the `-e` flags:

```bash
# In your ~/.zshrc or ~/.bashrc:
export SNAPTRADE_CLIENT_ID="your_client_id"
export SNAPTRADE_CONSUMER_KEY="your_consumer_key"

# Then register without -e flags:
claude mcp add snaptrade -s user -- snaptrade-mcp
```

### Claude Desktop

Add to your `claude_desktop_config.json` (Settings > Developer > Edit Config). This file lives in your user directory and is not part of any project.

```json
{
  "mcpServers": {
    "snaptrade": {
      "command": "snaptrade-mcp",
      "env": {
        "SNAPTRADE_CLIENT_ID": "your_client_id",
        "SNAPTRADE_CONSUMER_KEY": "your_consumer_key"
      }
    }
  }
}
```

Restart Claude Desktop. The SnapTrade tools will appear in the tools menu.

### Cursor

Add to `.cursor/mcp.json` in your project root. **Add `.cursor/mcp.json` to your `.gitignore`** so credentials don't get committed.

```json
{
  "mcpServers": {
    "snaptrade": {
      "command": "snaptrade-mcp",
      "env": {
        "SNAPTRADE_CLIENT_ID": "your_client_id",
        "SNAPTRADE_CONSUMER_KEY": "your_consumer_key"
      }
    }
  }
}
```

### ChatGPT (via streamable-http)

ChatGPT requires Streamable HTTP (`--transport streamable-http`) with OAuth 2.0.

**Step 1 — start a tunnel** with [ngrok](https://ngrok.com/) to get a public HTTPS URL:

```bash
ngrok http 8000
# note the forwarding URL, e.g. https://abc123.ngrok-free.app
```

**Step 2 — generate an OAuth client ID and secret** you will use for this connector:

```bash
python -c "import secrets; print('client_id=' + secrets.token_urlsafe(24)); print('client_secret=' + secrets.token_urlsafe(48))"
```

Save both values. You will use the same client ID and secret in ChatGPT and in your `.env` file below.

**Step 3 — create a connector** in ChatGPT (requires Pro, Team, Enterprise, or Edu):

1. Go to **Settings → Connectors** and click **New Connector**
2. Set the **MCP Server URL** to `https://abc123.ngrok-free.app/mcp`
3. Set **Authentication** to **OAuth** and note the **Callback URL** shown (e.g. `https://chatgpt.com/connector/oauth/xxxx`)
4. Fill in the OAuth client ID and secret fields with the values you generated in Step 2
5. Choose **Token endpoint auth method**: `client_secret_post`
6. Click **Create**

**Step 4 — start the server** with the same client ID and secret plus the callback URL from Step 3.

Fill in your `.env` file:

```bash
SNAPTRADE_CLIENT_ID=your_client_id
SNAPTRADE_CONSUMER_KEY=your_consumer_key
SNAPTRADE_OAUTH_CLIENT_ID=paste-the-client-id-from-step-2
SNAPTRADE_OAUTH_CLIENT_SECRET=paste-the-client-secret-from-step-2
SNAPTRADE_OAUTH_REDIRECT_URI=https://chatgpt.com/connector/oauth/xxxx
SNAPTRADE_PUBLIC_URL=https://abc123.ngrok-free.app
```

Then start the server:

```bash
set -a && source .env && set +a  # export all vars from .env to child processes
snaptrade-mcp --transport streamable-http
```

All four OAuth environment variables are required for Streamable HTTP. Set `SNAPTRADE_OAUTH_CLIENT_ID` and `SNAPTRADE_OAUTH_CLIENT_SECRET` to the exact values you generated in Step 2 and entered into the ChatGPT connector. Set `SNAPTRADE_OAUTH_REDIRECT_URI` to the Callback URL from Step 3 above (e.g. `https://chatgpt.com/connector/oauth/xxxx`). Set `SNAPTRADE_PUBLIC_URL` to your public-facing base URL (e.g. your ngrok URL) so OAuth discovery metadata advertises reachable endpoints.

Both `SNAPTRADE_OAUTH_REDIRECT_URI` and `SNAPTRADE_PUBLIC_URL` must be full `https://...` URLs. Invalid URL values can cause startup to fail before the CLI reaches its normal validation errors.

To customize the host or port:

```bash
snaptrade-mcp --transport streamable-http --host 0.0.0.0 --port 3000
```

## First-Time Setup

After installing, ask your AI agent:

> "Set up my SnapTrade connection"

This calls `snaptrade_setup`, which opens a browser window **on the machine running the server** where you authorize your brokerage. This works with ChatGPT too — the AI triggers the tool, but the browser opens locally. You only need to do this once. Your user credentials are saved locally at `~/.snaptrade/config.json`.

## Example Prompts

- "What brokerage accounts do I have?"
- "Show me my full portfolio summary"
- "What's my cash balance across all accounts?"
- "Analyze my portfolio for diversification risk"
- "What trades have I made recently?"
- "Search for Apple stock"
- "Which brokerages does SnapTrade support?"

## Troubleshooting

### Server fails to connect / "Failed to reconnect"

- Verify the package is installed: `python -c "from snaptrade_mcp.server import main; print('OK')"`
- If using a virtual environment, make sure `snaptrade-mcp` is installed in that environment.

### "Missing credentials" error

- Check that `SNAPTRADE_CLIENT_ID` and `SNAPTRADE_CONSUMER_KEY` are set in the `-e` flags (Claude Code) or `env` block (Claude Desktop / Cursor).

### "No config found" error

- Run `snaptrade_setup` through the MCP server first to connect a brokerage and create `~/.snaptrade/config.json`.

### "OAuth env vars required" / "PUBLIC_URL required" error

- These errors occur when using Streamable HTTP (`--transport streamable-http`) without the required OAuth environment variables. All four must be set:
  - `SNAPTRADE_OAUTH_CLIENT_ID` — the client ID you generated and entered into the ChatGPT connector
  - `SNAPTRADE_OAUTH_CLIENT_SECRET` — the matching client secret you generated and entered into the ChatGPT connector
  - `SNAPTRADE_OAUTH_REDIRECT_URI` — the Callback URL from your ChatGPT connector (Step 3 above)
  - `SNAPTRADE_PUBLIC_URL` — your public-facing base URL (e.g. your ngrok forwarding URL)

### "Invalid URL" startup error

- `SNAPTRADE_OAUTH_REDIRECT_URI` and `SNAPTRADE_PUBLIC_URL` must be valid absolute `https://` URLs.
- Example valid values:
  - `SNAPTRADE_OAUTH_REDIRECT_URI=https://chatgpt.com/connector/oauth/xxxx`
  - `SNAPTRADE_PUBLIC_URL=https://abc123.ngrok-free.app`

## Security

- **Read-only** — no trading, no account modification, no deletes
- **Credentials isolated** — API keys loaded from env vars, user secrets stored at `~/.snaptrade/config.json` (chmod 600). Neither appears in tool responses.
- **No dangerous operations** — cannot delete users, reset secrets, or modify anything

## Architecture

```text
snaptrade_mcp/
  server.py           # All 10 tools, 2 resources, 2 prompt templates
  oauth_provider.py   # In-memory OAuth 2.0 authorization server (for HTTP transport)
  __init__.py         # Package marker + version
  __main__.py         # Entry point (python -m snaptrade_mcp)
```

The server supports two transport modes:

- **STDIO** (default) — for local MCP clients (Claude Code, Claude Desktop, Cursor)
- **Streamable HTTP** (`--transport streamable-http`) — for remote clients (ChatGPT). Requires `SNAPTRADE_OAUTH_CLIENT_ID`, `SNAPTRADE_OAUTH_CLIENT_SECRET`, `SNAPTRADE_OAUTH_REDIRECT_URI` (callback URL from your OAuth client), and `SNAPTRADE_PUBLIC_URL` (your ngrok URL) for OAuth 2.0 authentication.

Each tool function calls the SnapTrade Python SDK, flattens the response into clean JSON, and returns it to the AI client.

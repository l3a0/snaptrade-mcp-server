# I Got Tired of Copy-Pasting My Portfolio Into ChatGPT, So I Wrote an MCP Server

*What I learned about the protocol that's quietly becoming the USB port for AI agents.*

---

I wanted daily AI analysis of my portfolio. It was tedious typing tickers, share counts, and cost bases every time into ChatGPT. So I forked [an existing open-source project](https://github.com/micah63/snaptrade-mcp-server) and extended it into a server that connects my brokerage accounts directly to any AI agent — Claude, ChatGPT — and lets it pull live portfolio data on demand.

Now I ask "analyze my portfolio for sector concentration risk" and the AI pulls the data, groups by sector, and flags where I'm overweight. The [project](https://github.com/l3a0/snaptrade-mcp-server) is built on a protocol called MCP that's worth understanding.

## What MCP Actually Is

MCP stands for **[Model Context Protocol](https://modelcontextprotocol.io)**. It's an open standard created by Anthropic that solves a specific problem: how do you give an AI agent access to external data and tools in a way that's standardized, secure, and works across different AI clients?

Before USB, every peripheral had its own proprietary connector. MCP does the same thing for AI integrations — one protocol that any AI client can use to talk to any data source.

An MCP server exposes **tools** — functions the AI can call, like "get my account balances" or "search for a stock ticker." (It also supports resources and prompt templates, but tools are the core primitive.) The AI decides when to call them based on the conversation.

## The Core Server

I started with 10 read-only tools wrapping the [SnapTrade](https://snaptrade.com) API. SnapTrade is a brokerage aggregation service (think [Plaid](https://plaid.com), but for investment accounts) that connects to brokerages like [Alpaca](https://alpaca.markets) and [Interactive Brokers](https://www.interactivebrokers.com) through a single API. I use it to pull data from Fidelity (read-only) and Schwab.

Here's what a tool looks like:

```python
from mcp.server.fastmcp import FastMCP  # https://github.com/modelcontextprotocol/python-sdk

mcp = FastMCP(
    "snaptrade",
    instructions="Read-only access to brokerage accounts via SnapTrade.",
)

@mcp.tool()
def snaptrade_get_positions(account_id: str) -> str:
    """Get current holdings for a specific account.

    Returns positions with symbol, quantity, market value, and price.
    """
    client, _ = _get_client()
    user_id, user_secret = _get_user()

    response = client.account_information.get_user_account_positions(
        account_id=account_id,
        user_id=user_id,
        user_secret=user_secret,
    )
    return _format_response({"account_id": account_id, "positions": _serialize(response)})
```

That `@mcp.tool()` decorator is doing the heavy lifting. It registers the function so any MCP-compatible client can discover and call it. The docstring becomes the tool's description — it's what the AI reads to decide when to use it. The server exposes 10 tools covering accounts, positions, orders, and transactions.

**The critical design constraint: every tool is read-only.** No trading, no account modification, no deletes. When you're piping financial data into an AI's context window, the attack surface matters. A bug or a [prompt injection](https://genai.owasp.org/llmrisk/llm01-prompt-injection/) can't accidentally sell your holdings if the server physically cannot place trades.

## CI, Security, and Documentation

A working server isn't enough if you can't trust it to stay working. Financial data raises the bar — you need confidence that changes don't break credential handling, that the CI catches regressions, and that you understand where your data goes.

I set up a **GitHub Actions CI pipeline** running automated code quality checks, type checking, build verification, and an import smoke test on every PR. The workflow uses explicit `permissions: contents: read` to follow the principle of least privilege. I added **security scanning** with [CodeQL](https://codeql.github.com) and automated **dependency updates** via [Dependabot](https://docs.github.com/en/code-security/dependabot) to catch vulnerabilities in third-party packages.

The test suite includes **unit tests** for CLI parsing, OAuth flows, and credential handling, plus **integration tests** that run against a real paper trading account — real API calls, real data, real credential handling. The integration tests use a temporary config file so they never touch your actual brokerage credentials.

**Security annotations** in the [server.py docstring](https://github.com/l3a0/snaptrade-mcp-server/blob/main/snaptrade_mcp/server.py) document the data flow, **credential storage trade-offs**, and the **audit logging gap**. Your portfolio data flows through two intermediaries — SnapTrade's API servers, then whatever AI client you connect — and each has different retention and training policies. The docstring covers all of this so you can make an informed decision about which clients to connect.

## Making It Work With ChatGPT

[Claude Code](https://docs.anthropic.com/en/docs/claude-code/overview) and Cursor use **[STDIO transport](https://modelcontextprotocol.io/docs/concepts/transports)** — they launch the MCP server as a local subprocess and communicate over standard input/output. Simple, fast, no networking involved.

ChatGPT uses **[Streamable HTTP transport](https://modelcontextprotocol.io/docs/concepts/transports)**. The server runs as an HTTP service, ChatGPT connects over the network, and everything needs [OAuth 2.0](https://oauth.net/2/) authentication. This required building three new things:

**An OAuth provider.** I vibe coded a `SimpleOAuthProvider` class using Claude Code in VS Code — an in-memory OAuth 2.0 authorization server designed for single-user deployments. It handles client registration, authorization code grants, token exchange, and refresh tokens. All in memory, intentionally — tokens are lost on server restart, and clients just re-authenticate. For a personal portfolio tool, that's the right trade-off.

**Transport security.** ChatGPT's servers need to reach your MCP server over the internet, but the server runs on your laptop. It has no public IP, it's behind NAT and a firewall. [ngrok](https://ngrok.com) solves this by creating a secure tunnel — you run `ngrok http 8000` and it gives you a public URL like `https://abc123.ngrok-free.app` that forwards traffic to your local port. No DNS configuration, no port forwarding, no cloud deployment.

Exposing a local server creates a new risk: DNS rebinding attacks. Your browser enforces a same-origin policy — code from `evil.com` can't make requests to `localhost:8000`. DNS rebinding gets around this.

An attacker sets up `evil.com` so it initially resolves to their own server, then switches the DNS record to point to `127.0.0.1`. Your browser already loaded the page from `evil.com`, so when the page's JavaScript makes a follow-up request, it goes to your local machine instead — and the browser thinks it's still talking to `evil.com`, so same-origin policy doesn't block it. Now a remote attacker's code is hitting your local MCP server, which has access to your portfolio data.

The MCP SDK provides `TransportSecuritySettings` to defend against this. It checks the `Host` header on incoming requests and only allows traffic from explicitly trusted origins — in my case, the ngrok hostname and localhost. Anything else gets rejected before it reaches a tool.

**Startup validation.** The server validates three layers of credentials at startup — app credentials, user brokerage credentials, and OAuth transport credentials — and fails fast with clear errors if any are missing or malformed.

Here's the short version of the ChatGPT setup: start an ngrok tunnel (`ngrok http 8000`), generate OAuth credentials, enable Developer Mode in ChatGPT (**Settings → Apps**), and create a new app pointing to your ngrok URL.

![ChatGPT Developer Mode settings](images/chatgpt-developer-mode.png)

In the app configuration, set Authentication to OAuth, expand Advanced settings, and configure the OAuth client:

![ChatGPT OAuth client registration settings](images/chatgpt-oauth-settings.png)

The key fields: set **Registration method** to `User-Defined OAuth Client`, paste in the OAuth client ID and secret you generated, and set **Token endpoint auth method** to `client_secret_post`. Scroll down to confirm the OAuth endpoints were auto-discovered from your server — they should all show your ngrok hostname.

![ChatGPT OAuth endpoints auto-discovered from the MCP server](images/chatgpt-oauth-endpoints.png)

Then fill in your `.env` with all the credentials and start the server:

```bash
set -a && source .env && set +a  # export all vars so child processes inherit them
snaptrade-mcp --transport streamable-http
```

Click **Create** in ChatGPT, and you're connected. The [README](https://github.com/l3a0/snaptrade-mcp-server#chatgpt-via-streamable-http) has the full step-by-step with every field and environment variable spelled out.

## What This Tells Us About Where AI Is Heading

MCP is interesting not because of what it does today — connecting a brokerage to ChatGPT is a nice convenience — but because of what it implies about how AI tools will work in general.

Right now, most AI interactions are text-in, text-out. You type a question, you get an answer. MCP turns AI from a conversational partner into an **agent that can act on your data**. The same protocol that connects my brokerage could connect your CRM, your codebase, your email, your analytics dashboard.

The protocol is deliberately simple. A tool is a function with a docstring. The AI reads the description, decides when to call it, and parses the JSON response. No special training, no fine-tuning, no plugins marketplace with a review process. The barrier to giving AI access to your data drops from "build an integration with each AI provider's proprietary plugin system" to "write a function and decorate it." The complexity lies in writing the server that orchestrates and connects to the data sources.

The ecosystem is already scaling up. [OpenClaw](https://github.com/openclaw/openclaw) — an open-source AI agent that hit 250,000+ GitHub stars by early 2026 — shows where this goes next. OpenClaw runs as a persistent background process that connects to messaging apps like WhatsApp, Telegram, and Discord. You send it a message, and it orchestrates multi-step workflows using MCP servers as its tool layer.

What makes this an agent rather than a pipeline is the **ReAct loop** — the model *reasons* about what to do next, *acts* by calling a tool, *observes* the result, then repeats until the task is done. Each step is decided dynamically based on the previous result, not hardcoded.

MCP is becoming the USB port, and frameworks like OpenClaw are the operating systems that plug into it. My SnapTrade MCP server is just one peripheral in this stack — it doesn't care whether the agent calling it is ChatGPT, Claude, or an OpenClaw agent orchestrating a complex financial workflow.

This also brings real security risks. In February 2026, researchers found [341 malicious skills on ClawHub](https://thehackernews.com/2026/02/researchers-find-341-malicious-clawhub.html) designed to steal credentials via prompt injection. Nvidia responded with [NemoClaw](https://nvidianews.nvidia.com/news/nvidia-announces-nemoclaw), a security add-on with sandboxing built specifically for OpenClaw deployments. The more powerful the orchestration, the more the attack surface matters — which is exactly why I kept this MCP server read-only from the start.

## Try It Yourself

The whole project is open source: [github.com/l3a0/snaptrade-mcp-server](https://github.com/l3a0/snaptrade-mcp-server). The [README](https://github.com/l3a0/snaptrade-mcp-server#readme) has setup instructions for ChatGPT, Claude Code, Cursor, and other MCP-compatible clients.

The code is MIT-licensed. If you've got a different API you wish your AI could talk to, the pattern is the same: wrap your API calls in functions, decorate them with `@mcp.tool()`, and let the protocol handle the rest.

---

*If this was useful, please share it with someone who's been manually feeding data to their AI. If you build your own MCP server, I'd love to hear what you connected. And if you'd like to support this newsletter, paid subscriptions help cover the AI tokens and experiment costs that go into these posts.*

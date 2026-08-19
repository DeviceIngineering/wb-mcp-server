[Русский](README.md) · [中文](README.zh.md)

# WB MCP Server

[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](pyproject.toml)
[![MCP tools](https://img.shields.io/badge/MCP%20tools-202-orange.svg)](docs/tools.md)
[![Transport](https://img.shields.io/badge/transport-SSE-lightgrey.svg)](#how-it-works)

**Run your Wildberries stores from a chat with an AI assistant.**
202 tools covering the Wildberries Seller API — product cards, prices, ads, shipments,
reviews, finance, analytics — exposed to Claude, Cursor, Copilot, Gemini CLI and any
other MCP client. Built for WB sellers (Wildberries is Russia's largest marketplace)
who run one or several seller accounts and would rather ask a question than click
through the seller portal.

> This is the author's own working tool. It is used every day and updated as the author
> needs it — see [Updates and support](#updates-and-support).

```
You: Which of my product cards are blocked, and why?
You: Show ad cost share for every campaign this week and pause the ones above 15%.
You: Which warehouses currently have an intake coefficient of 0 or 1?
You: Reply to every new 5-star review with a thank-you note.
```

![WB MCP Server dashboard](docs/img/dashboard.png)

---

## What it can do

202 tools, grouped by Wildberries Seller API area.
The full numbered list with a description of each one is in **[docs/tools.md](docs/tools.md)**.

| Area | Tools | What it covers |
|---|---:|---|
| Product cards | 26 | card list and details, create and update, SEO text, attributes, barcodes, media, tags, trash bin, **cards with errors and blocks** |
| Prices and discounts | 7 | current prices, setting prices and discounts, price quarantine, WB Club (WB's paid membership discounts), B2B, upload status |
| Promotions | 7 | promotion calendar, auto-promotions, an audit of "where WB has already enrolled your products", joining and leaving a promotion |
| Advertising | 22 | campaign list and creation, statistics and ad cost share, bids and bid recommendations, keyword clusters and negative phrases, balance and top-ups |
| Analytics | 25 | sales funnel v3 (per-product views → cart → order conversion), day-by-day history, stock, anti-fraud, paid intake, measurement penalties, brand share, sales by region, search queries |
| Statistics | 3 | sales, orders, stock (statistics-api) |
| FBS orders | 29 | new and all assembly tasks, statuses, cancellation, labels, supplies, boxes, warehouse passes, KIZ marking codes (Russia's mandatory product marking). FBS = fulfilled by seller from WB warehouse pickup |
| DBS orders | 10 | delivery by seller: orders, statuses, actions, delivery dates, metadata |
| Click & collect | 9 | pickup orders, buyer identity confirmation, actions and metadata |
| FBW supplies | 6 | shipments into WB warehouses, goods in a shipment, warehouses, **intake coefficients for the next 14 days** |
| Seller warehouses and stock | 8 | seller warehouses, updating and reading stock |
| Finance | 7 | sales reports, detailed breakdown, acquiring, balance, seller profile |
| Tariffs and storage | 6 | box and pallet tariffs, return tariffs, commissions, FBW transit, paid storage |
| Reviews and questions | 18 | reviews and questions, replies, per-period counters, archive, pinned reviews, seller rating |
| Returns | 3 | return requests, answering a request, returns report |
| Buyer chats | 4 | chats, events, sending messages, downloading attachments |
| Documents | 4 | document categories, list, single and bulk download |
| Users | 2 | staff members and invitations |
| WB Jam | 1 | WB Jam subscription status (WB's paid analytics add-on) |
| Shops | 1 | list of connected seller accounts |
| Diagnostics | 4 | self-diagnostics, token inspection, tool degradations, WB API news |

Three things similar servers usually do not have:

- **Multi-store.** Every call takes a `shop_id`, so two WB seller accounts live in one
  conversation. With a single store you can omit `shop_id` entirely.
- **WB API diagnostics.** The server pings WB hosts by itself, sends one cheap probe
  request per API category, decodes the token's expiry and scopes, and highlights
  "degradations": a tool that used to work and now fails consistently — a reliable sign
  that WB changed the API.
- **Encrypted tokens.** WB tokens are stored encrypted (Fernet), not in your client's config.

## Quick start

You need Docker (Docker Desktop or OrbStack) and a Wildberries Seller API token.

> **Before the first run.** A build from scratch currently pulls the `mcp` 2.x library,
> which the server does not start with. The workaround and the details are in
> [How it works](#how-it-works), under the `mcp` version note.

```bash
git clone https://github.com/DeviceIngineering/wb-mcp-server.git
cd wb-mcp-server
cp .env.example .env          # fine as-is for a local run
docker compose up -d --build
```

Check:

```bash
curl -s http://localhost:8001/api/health
# {"status":"ok","auth_enabled":false,"health_check_interval_min":30,...}
```

What you now have:

| Address | What it is |
|---|---|
| <http://localhost:8001> | dashboard: tool calls, errors, response times |
| <http://localhost:8001/shops> | stores: add a WB seller account, test its token |
| <http://localhost:8001/diagnostics> | diagnostics: tokens, WB host pings, probes, history |
| <http://localhost:8001/api/health> | JSON summary for external monitoring |
| `http://localhost:8001/sse` | **the MCP endpoint** — this is what you give to the client |

Next:

1. Open <http://localhost:8001/shops> → **Добавить магазин** (Add store) → paste the WB
   token → **Проверить** (Test). The token comes from the WB Seller Portal
   (seller.wildberries.ru): **Настройки → Доступ к API → Создать токен**
   (Settings → API access → Create token). It is valid for 180 days; the remaining
   lifetime is shown on the diagnostics page.
2. Connect an MCP client — see the next section.
3. Ask your assistant: "list my Wildberries stores" — the `wb_list_shops` tool should fire.

The start command, flag by flag:

| Flag | Why |
|---|---|
| `up` | start the service described in `docker-compose.yml` |
| `-d` | in the background, without holding the terminal |
| `--build` | build the image from `Dockerfile` — needed on the first run and after code updates |

Stop it with `docker compose down` (data stays in the `wb_data` volume).
Logs: `docker compose logs -f`.

<details>
<summary>Running without Docker</summary>

```bash
git clone https://github.com/DeviceIngineering/wb-mcp-server.git
cd wb-mcp-server
python3 -m venv .venv && source .venv/bin/activate
pip install .
DATA_DIR=./data PORT=8001 python -m wb_mcp.app
```

`DATA_DIR` is mandatory here: by default the server writes to `/data`, a path that only
exists inside the container.
</details>

## Installing into clients

The server speaks MCP over **SSE**: `GET /sse` is the event stream, `POST /messages`
carries the client's messages. SSE support differs from client to client, so each one
has its own guide — with config paths for macOS, Linux and Windows, ready-to-paste JSON,
and variants with and without an auth token.

> The per-client guides in `docs/` are currently **in Russian only**. The configuration
> in them is ready-made JSON with file paths and flags, which is readable regardless
> of language.

| Client | SSE directly | Guide |
|---|---|---|
| Claude Code | yes | [docs/claude-code.md](docs/claude-code.md) |
| Claude Desktop | no → `mcp-remote` bridge or local stdio | [docs/claude-desktop.md](docs/claude-desktop.md) |
| Cursor | yes | [docs/cursor.md](docs/cursor.md) |
| Windsurf | yes | [docs/windsurf.md](docs/windsurf.md) |
| VS Code (GitHub Copilot) | yes | [docs/vscode-copilot.md](docs/vscode-copilot.md) |
| Cline | yes | [docs/cline.md](docs/cline.md) |
| Continue.dev | yes | [docs/continue.md](docs/continue.md) |
| Zed | by URL; SSE support is not officially stated | [docs/zed.md](docs/zed.md) |
| JetBrains AI Assistant | yes (SSE as legacy) | [docs/jetbrains.md](docs/jetbrains.md) |
| Gemini CLI | yes | [docs/gemini-cli.md](docs/gemini-cli.md) |
| Codex CLI | no → `mcp-remote` bridge | [docs/codex.md](docs/codex.md) |

Overview and compatibility table: [docs/README.md](docs/README.md).

The shortest possible setup, Claude Code:

```bash
claude mcp add --transport sse wildberries http://localhost:8001/sse
```

## Multi-store and security

**Several seller accounts.** Stores are added on `/shops`; each one gets its own `shop_id`.
`wb_list_shops` returns the list, and 200 of the 202 tools take `shop_id` as their first
parameter (the exceptions are `wb_list_shops` and `wb_degradations`).
With a single store the parameter can be omitted — the server substitutes the only one available.

**Where the tokens live.** In the `wb_data` volume (`/data` inside the container):

- `shops.json` — stores, with tokens encrypted using Fernet;
- `.encryption_key` — the encryption key, generated on first start;
- `stats.db` — SQLite with call statistics and diagnostics history.

The key sits next to the encrypted data, so the encryption protects against an accidental
leak of the single `shops.json` file (a backup, a copy-paste) but not against anyone who
gets access to the whole volume. Move the data as a whole volume — see [DEPLOY.md](DEPLOY.md).

**MCP authorization.** The `MCP_AUTH_TOKEN` variable in `.env`:

```bash
openssl rand -hex 32   # put the value into .env → MCP_AUTH_TOKEN=
docker compose up -d
```

- empty (the default) — `/sse` is open to anyone with network access to the port;
- set — the client must send `Authorization: Bearer <token>` **or** `?token=<token>`
  in the URL. The second form rescues clients that cannot send custom headers.

**What the server does not do:**

- The web UI (`/`, `/shops`, `/diagnostics`) and `POST /messages` are **not** protected by
  the token: the check runs only on `GET /sse`. Keep port 8001 inside a trusted network.
- Port 8001 is not meant to be exposed to the internet. For remote access use Tailscale or a VPN.
- The server does not terminate HTTPS. If you need TLS from outside, put a reverse proxy in front.

## How it works

One Docker container running a FastAPI application that plays two roles at once:
an MCP server over SSE, and a small web UI. One paragraph per file:

- **`wb_mcp/server.py`** — the MCP server itself. The `TOOLS` list of 202 `Tool` objects
  (name, description, JSON schema of arguments) is exactly what the client receives in
  response to `tools/list`. Calls are routed by three dictionaries: `NO_CLIENT_DISPATCH`
  (no WB access needed), `CLIENT_DISPATCH` (needs the store's HTTP client) and
  `SHOP_DISPATCH` (needs the `shop_id` as well). The stdio entry point `main()` lives here
  too, for clients that only speak stdio.
- **`wb_mcp/client.py`** — HTTP clients for the 14 Wildberries hosts. One `WBClient` per
  store, wrapping an `httpx.AsyncClient` with the token; clients are cached in a pool keyed
  by `shop_id`.
- **`wb_mcp/app.py`** — FastAPI: `GET /sse` and `POST /messages` for MCP, the dashboard,
  stores and diagnostics pages, the `/api/*` JSON API, the `MCP_AUTH_TOKEN` check, and the
  background health-check loop.
- **`wb_mcp/settings.py`** — stores and keys: reading and writing `shops.json`, Fernet
  encryption, migration of the old single-store `settings.json`, masking tokens for the UI.
  There is a fallback: if `WB_API_TOKEN` is set, a store named `default` appears.
- **`wb_mcp/diagnostics.py`** — pinging WB hosts, decoding the JWT token (expiry, scopes,
  sandbox flag), "probes" — one cheap real request per API category — and WB news.
- **`wb_mcp/stats.py`** — SQLite via aiosqlite: every tool call is recorded with its
  duration, success flag and `shop_id`; this feeds the degradation detector and the
  health-check history.
- **`wb_mcp/templates/`** — three PicoCSS pages, no frontend build step.

Non-obvious details:

- **`shop_id` is filled in automatically while there is only one store.** Convenient day
  to day, but the moment you add a second account, calls without `shop_id` start returning
  "Укажите shop_id" ("specify shop_id").
- **Every call is written to the statistics**, failures included. That is what powers the
  degradation detector: "used to work, now fails consistently" is a signal that WB changed
  the API, not that you made a mistake. Check `wb_degradations` or the dashboard.
- **Background diagnostics every 30 minutes** make real requests to WB and consume your
  rate limits. If that is in the way, set `HEALTH_CHECK_INTERVAL_MIN=0` in `.env`.
- **Responses are returned as-is**, the raw JSON from WB, with no repackaging. That keeps
  the tools predictable, but large reports should be requested with filters or the answer
  will eat your context window.
- **The container log prints, on every MCP message,** `RuntimeError: Unexpected ASGI
  message 'http.response.start' sent, after response already completed`. This is a
  consequence of `POST /messages` being wrapped in a FastAPI route instead of being mounted
  as an ASGI app. By that point the message has already been accepted (`202 Accepted`) and
  processed — in a check with the official Python MCP client (`mcp` 1.29.0), `initialize`,
  `tools/list` and a tool call all worked normally. The connection is dropped on each POST
  though, so clients that reuse keep-alive connections may trip over it. The log line is
  expected, not a sign of breakage.
- **The `mcp` library version — a known issue.** The server is written against the
  decorator API of `mcp` 1.x (`@app.list_tools()`), which was removed in `mcp` 2.0.
  `pyproject.toml` declares `mcp[cli]>=1.0.0` with no upper bound, so a fresh install pulls
  `mcp` 2.x and crashes on start with
  `AttributeError: 'Server' object has no attribute 'list_tools'`.
  Until the constraint lands in `pyproject.toml`, install the 1.x line explicitly:

  ```bash
  pip install "mcp[cli]<2.0.0"          # local run
  ```

  For Docker, add the same line to the `Dockerfile` after `pip install .`, or wait for the
  fix in the repository.

Environment variables:

| Variable | Default | Meaning |
|---|---|---|
| `WB_API_TOKEN` | empty | token for the `default` store; adding stores via `/shops` is more convenient |
| `MCP_AUTH_TOKEN` | empty | Bearer token for `/sse`; empty means authorization is off |
| `HEALTH_CHECK_INTERVAL_MIN` | `30` | background diagnostics interval, `0` disables it |
| `DATA_DIR` | `/data` | directory holding `shops.json`, `.encryption_key`, `stats.db` |
| `PORT` | `8001` | HTTP server port |

## Wildberries API limits

These are limits of WB itself, not of this server — but the assistant will hit them
regularly, and it is better to know them in advance.

- `GET /adv/v3/fullstats` (advertising statistics) — **3 requests per minute**, period
  no longer than 31 days.
- Sales funnel v3 — **3 requests per minute**; day-by-day history is available for the
  last week at most.
- `/ping` — 3 requests per 30 seconds per host (the background diagnostics accounts for this).
- **Any 4XX response counts as 10 requests** against the limit (a rule in force since
  2026-06-04). One wrong parameter inside a loop and you are rate-limited.
- `reportDetailByPeriod` is being removed on 2026-07-15; the server already calls
  finance-api with a fallback to the old endpoint.
- FBW supplies cannot be created through the API — only in the seller portal.
  The `wb_fbw_*` tools are informational.
- A WB token lives for 180 days. `wb_token_info` and the `/diagnostics` page show
  the remaining time.
- A `429` from WB means a rate limit, not a failure. Retry in a minute.

Verified against the dev.wildberries.ru documentation as of June 2026.

## Technical reference

### Wildberries Seller API hosts

| API | Base URL |
|-----|-------------|
| Content | content-api.wildberries.ru |
| Marketplace (FBS/DBS/DBW) | marketplace-api.wildberries.ru |
| Supplies (FBW) | supplies-api.wildberries.ru |
| Statistics | statistics-api.wildberries.ru |
| Analytics | seller-analytics-api.wildberries.ru |
| Prices | discounts-prices-api.wildberries.ru |
| Promotions calendar | dp-calendar-api.wildberries.ru |
| Advert | advert-api.wildberries.ru |
| Finance | finance-api.wildberries.ru |
| Feedbacks + Questions | feedbacks-api.wildberries.ru |
| Returns | returns-api.wildberries.ru |
| Tariffs / News / Seller | common-api.wildberries.ru |
| Buyer Chat | buyer-chat-api.wildberries.ru |
| Documents | documents-api.wildberries.ru |

### Diagnostics

- **The `/diagnostics` page** — per store: token expiry and scopes, pings of all WB API
  hosts, per-category probes, check history, and a "check now" button.
- **Automatic background checks** every `HEALTH_CHECK_INTERVAL_MIN` minutes.
- **Degradation detector** — highlights on the dashboard the tools that stopped working.
- **MCP tools**: `wb_diagnostics`, `wb_token_info`, `wb_degradations`, `wb_api_news`.
- **`GET /api/health`** — JSON summary for external monitoring.
- **`POST /api/diagnostics/run`** — run a check of all stores right now.
- **`GET /api/diagnostics/<shop_id>`** — full diagnostics of a single store.

### Project layout

```
wb-mcp-server/
├── docker-compose.yml          # port 8001, wb_data volume
├── Dockerfile                  # python:3.12-slim
├── pyproject.toml
├── DEPLOY.md                   # deploying to a dedicated machine, moving the data
├── docs/                       # client setup guides + tool reference
└── wb_mcp/
    ├── server.py       # MCP server: 202 tools, dispatch tables, stdio mode
    ├── client.py       # HTTP clients for the 14 Wildberries APIs
    ├── app.py          # FastAPI: SSE + web UI + auth + health loop
    ├── diagnostics.py  # pings, JWT decoder, probes, API news
    ├── settings.py     # stores and keys (Fernet)
    ├── stats.py        # call statistics and check history (SQLite)
    └── templates/      # PicoCSS: dashboard, diagnostics, shops
```

### Deployment

Moving the server to a dedicated machine, migrating stores, setting up autostart —
see **[DEPLOY.md](DEPLOY.md)** (in Russian).

## Updates and support

Wildberries changes its API constantly: endpoints are added, renamed and switched off —
the limits section above lists what has already been caught in practice.
This server is the author's working tool, and it is updated **as the author needs it**:
when the next change breaks something in his own stores. There is no schedule and no
commitment on timing.

If you need a fix urgently, write to **d0371153@gmail.com**.
Issues and pull requests are welcome and do get reviewed.

## License

MIT — see [LICENSE](LICENSE).

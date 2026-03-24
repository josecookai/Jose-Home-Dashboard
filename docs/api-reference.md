# API Reference

Documentation for all external APIs used by Jose Home Dashboard scripts.

---

## 1. Telegram Bot API

**Base URL:** `https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}`

**Auth method:** Bot token embedded in the URL path. Obtain a token from [@BotFather](https://t.me/BotFather).

**Env vars:**
- `TELEGRAM_BOT_TOKEN` — bot token issued by BotFather
- `TELEGRAM_CHAT_ID` — target chat or channel ID (string, may be negative for groups)

### Key Endpoint: Send Message

```
POST /bot{token}/sendMessage
```

**Request body (JSON):**

```json
{
  "chat_id": "-1001234567890",
  "text": "Hello from the dashboard!",
  "parse_mode": "Markdown",
  "disable_web_page_preview": true
}
```

`parse_mode` options:
- `"Markdown"` — legacy Markdown (single asterisks, backticks, underscores)
- `"MarkdownV2"` — stricter Markdown v2 (requires escaping special chars)
- `"HTML"` — `<b>`, `<i>`, `<code>`, `<a href="...">` tags

**Response (JSON):**

```json
{
  "ok": true,
  "result": {
    "message_id": 42,
    "chat": { "id": -1001234567890, "type": "channel" },
    "date": 1711234567,
    "text": "Hello from the dashboard!"
  }
}
```

**Rate limits:** 30 messages/second per bot; 20 messages/minute per chat.

---

## 2. Strava API

**Base URL:** `https://www.strava.com/api/v3`

**Auth method:** OAuth 2.0. Access tokens expire after 6 hours; use the refresh token flow to obtain a new one automatically.

**Env vars:**
- `STRAVA_CLIENT_ID` — app client ID from Strava developer portal
- `STRAVA_CLIENT_SECRET` — app client secret
- `STRAVA_ACCESS_TOKEN` — short-lived bearer token (refreshed automatically)
- `STRAVA_REFRESH_TOKEN` — long-lived token used to obtain new access tokens

### Token Refresh

```
POST https://www.strava.com/oauth/token
```

**Request body (form-encoded):**

```
client_id=<STRAVA_CLIENT_ID>
client_secret=<STRAVA_CLIENT_SECRET>
refresh_token=<STRAVA_REFRESH_TOKEN>
grant_type=refresh_token
```

**Response:**

```json
{
  "access_token": "new_access_token",
  "refresh_token": "possibly_rotated_refresh_token",
  "expires_at": 1711240000
}
```

### Key Endpoint: List Athlete Activities

```
GET /athlete/activities
```

**Headers:** `Authorization: Bearer {STRAVA_ACCESS_TOKEN}`

**Query params:**
- `per_page` (int, max 200) — number of activities to return
- `after` (Unix timestamp) — return activities after this time
- `before` (Unix timestamp) — return activities before this time

**Response (array of activity objects):**

```json
[
  {
    "id": 9876543210,
    "name": "Morning Run",
    "type": "Run",
    "distance": 8047.0,
    "moving_time": 2700,
    "elapsed_time": 2850,
    "total_elevation_gain": 45.2,
    "start_date": "2024-03-24T07:00:00Z",
    "average_heartrate": 152.0,
    "average_speed": 2.98
  }
]
```

**Rate limits:** 100 requests/15 min; 1,000 requests/day.

---

## 3. Polymarket API

**Base URL:** `https://clob.polymarket.com`

**Auth method:** None required for public market data.

**Env vars:** None required for read-only access.

### Key Endpoint: List Markets

```
GET /markets
```

**Query params:**
- `next_cursor` — pagination cursor for next page
- `active` (bool) — filter to active markets only
- `closed` (bool) — filter to closed markets
- `tag_id` — filter by tag/category ID

**Response:**

```json
{
  "limit": 100,
  "count": 100,
  "next_cursor": "abc123",
  "data": [
    {
      "condition_id": "0x1234...",
      "question_id": "0xabcd...",
      "question": "Will X happen by date Y?",
      "description": "Market description text.",
      "end_date_iso": "2024-12-31T23:59:59Z",
      "active": true,
      "closed": false,
      "tokens": [
        {
          "token_id": "YES_token_id",
          "outcome": "Yes",
          "price": 0.72,
          "winner": false
        },
        {
          "token_id": "NO_token_id",
          "outcome": "No",
          "price": 0.28,
          "winner": false
        }
      ],
      "volume": 1250000.0,
      "liquidity": 45000.0
    }
  ]
}
```

Key fields:
- `tokens[].price` — implied probability (0–1), where `Yes.price` is the market's current probability the event occurs
- `volume` — total trading volume in USD
- `liquidity` — current order book liquidity in USD

**Rate limits:** Not officially published; stay below ~60 requests/minute to avoid throttling.

---

## 4. Yahoo Finance (yfinance)

**Library:** `yfinance` (Python package, wraps Yahoo Finance undocumented API)

**Auth method:** None required.

**Env vars:** None required.

**Installation:** `pip install yfinance`

### Basic Usage

```python
import yfinance as yf

ticker = yf.Ticker("AMZN")

# Historical OHLCV data
hist = ticker.history(period="1mo", interval="1d")
# Returns a pandas DataFrame with columns: Open, High, Low, Close, Volume, Dividends, Stock Splits

# Options chain for a specific expiry
expiry_dates = ticker.options          # tuple of expiry date strings, e.g. ("2024-04-19", ...)
chain = ticker.option_chain("2024-04-19")
calls = chain.calls    # DataFrame of call contracts
puts  = chain.puts     # DataFrame of put contracts
```

**`ticker.history()` parameters:**
- `period` — `"1d"`, `"5d"`, `"1mo"`, `"3mo"`, `"6mo"`, `"1y"`, `"2y"`, `"5y"`, `"max"`
- `interval` — `"1m"`, `"5m"`, `"15m"`, `"1h"`, `"1d"`, `"1wk"`, `"1mo"`
- `start` / `end` — explicit date strings, e.g. `"2024-01-01"`

**Options chain DataFrame columns:**
`contractSymbol`, `strike`, `lastPrice`, `bid`, `ask`, `impliedVolatility`, `inTheMoney`, `openInterest`, `volume`

**Rate limits:** Unofficial; Yahoo Finance enforces rate limits on IPs. Cache results locally and avoid hammering in short loops.

---

## 5. GitHub API

**Base URL:** `https://api.github.com`

**Auth method:** Personal access token (PAT) via `Authorization` header. Unauthenticated requests are heavily rate-limited.

**Env vars:**
- `GITHUB_TOKEN` — personal access token (classic or fine-grained)

### Key Endpoint: Search Repositories

```
GET /search/repositories
```

**Headers:** `Authorization: Bearer {GITHUB_TOKEN}`

**Query params:**
- `q` (required) — search query, e.g. `"language:python stars:>1000 created:>2024-01-01"`
- `sort` — `"stars"`, `"forks"`, `"help-wanted-issues"`, `"updated"`
- `order` — `"desc"` (default) or `"asc"`
- `per_page` (max 100) — results per page
- `page` — page number

**Example request:**

```
GET /search/repositories?q=language:python+topic:machine-learning&sort=stars&order=desc&per_page=10
```

**Response:**

```json
{
  "total_count": 48932,
  "incomplete_results": false,
  "items": [
    {
      "id": 123456789,
      "full_name": "owner/repo-name",
      "html_url": "https://github.com/owner/repo-name",
      "description": "A great ML library",
      "stargazers_count": 95000,
      "forks_count": 12000,
      "language": "Python",
      "topics": ["machine-learning", "deep-learning"],
      "created_at": "2019-06-01T00:00:00Z",
      "updated_at": "2024-03-20T12:00:00Z",
      "pushed_at": "2024-03-20T10:00:00Z"
    }
  ]
}
```

**Rate limits:**
- Authenticated: 30 search requests/minute; 5,000 general requests/hour
- Unauthenticated: 10 search requests/minute; 60 general requests/hour

---

## 6. HuggingFace API

**Base URL:** `https://huggingface.co`

**Auth method:** API token via `Authorization` header for write operations or private repos. Public model listing requires no auth.

**Env vars:** None required for public listing (add `HUGGINGFACE_TOKEN` if accessing private repos or needing higher limits).

### Key Endpoint: List Models

```
GET /api/models
```

**Query params:**
- `sort` — field to sort by; use `"trending_score"` for trending, `"downloads"` for most downloaded, `"likes"` for most liked
- `direction` — `-1` (descending, default) or `1` (ascending)
- `limit` (max 100) — number of results to return
- `filter` — filter by tag, e.g. `"text-generation"`, `"image-classification"`
- `search` — keyword search on model names/descriptions
- `full` — `"True"` to include all metadata fields

**Example request:**

```
GET /api/models?sort=trending_score&direction=-1&limit=20&filter=text-generation
```

**Response (array of model objects):**

```json
[
  {
    "id": "mistralai/Mistral-7B-Instruct-v0.2",
    "modelId": "mistralai/Mistral-7B-Instruct-v0.2",
    "author": "mistralai",
    "sha": "abc123...",
    "lastModified": "2024-03-15T10:00:00.000Z",
    "tags": ["transformers", "text-generation", "mistral"],
    "pipeline_tag": "text-generation",
    "downloads": 5200000,
    "likes": 8400,
    "trending_score": 142.5,
    "private": false
  }
]
```

**Rate limits:** Unauthenticated requests are limited to approximately 300 requests/hour per IP. With a token the limit is higher (exact figure not published).

---

## 7. CoinGecko API

**Base URL:** `https://api.coingecko.com/api/v3`

**Auth method:** No authentication required for the free public API. A Pro API key (`x-cg-pro-api-key` header) unlocks higher rate limits.

**Env vars:** None required for free tier.

### Key Endpoint: Simple Price

```
GET /simple/price
```

**Query params:**
- `ids` (required) — comma-separated CoinGecko coin IDs, e.g. `"bitcoin,ethereum,solana"`
- `vs_currencies` (required) — comma-separated target currencies, e.g. `"usd,eur"`
- `include_market_cap` — `"true"` to include market cap
- `include_24hr_vol` — `"true"` to include 24-hour volume
- `include_24hr_change` — `"true"` to include 24-hour price change percentage
- `include_last_updated_at` — `"true"` to include last updated Unix timestamp

**Example request:**

```
GET /simple/price?ids=bitcoin,ethereum&vs_currencies=usd&include_24hr_change=true
```

**Response:**

```json
{
  "bitcoin": {
    "usd": 67500.0,
    "usd_24h_change": 2.35
  },
  "ethereum": {
    "usd": 3520.0,
    "usd_24h_change": 1.12
  }
}
```

### Other Useful Endpoint: Coin Market Data

```
GET /coins/{id}
```

Returns full market data for a single coin including price, market cap, volume, circulating supply, all-time high, and community stats.

```
GET /coins/bitcoin
```

**Rate limits:**
- Free tier: 30 calls/minute, 10,000 calls/month
- Demo API key (free registration): 30 calls/minute with relaxed monthly cap
- Pro tier: up to 500 calls/minute

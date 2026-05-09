# ProxyMaze'26 — Full Implementation Plan

> **Goal:** Build a real-time proxy monitoring HTTP API service that continuously health-checks proxy endpoints, fires/resolves alerts on threshold breaches, delivers webhooks, and speaks Slack & Discord. Target: **270/270 points**.

---

## Challenge Summary

| Metric | Value |
|---|---|
| Core Points | 250 |
| Bonus Points | +20 (Slack +10, Discord +10) |
| Passing Score | 180 |
| Target Score | **270** |
| Evaluation | **Black-box** — only the HTTP API is tested |
| Threshold | Failure rate ≥ 0.20 fires alert; < 0.20 resolves |

---

## Technology Choice

| Layer | Technology | Rationale |
|---|---|---|
| Runtime | **Node.js 20+** | Fast async I/O, excellent for concurrent HTTP probes |
| Framework | **Express.js** | Lightweight, zero-opinion, fast to wire 13 endpoints |
| Language | **JavaScript (ES Modules)** | No build step, keeps it simple |
| Storage | **In-memory** (Maps, Arrays) | No DB needed — the challenge is stateless across restarts |
| HTTP Client | **undici** | Superior timeout control, DNS handling, connection pooling vs native `fetch` |
| Concurrency | **p-limit** | Prevents socket exhaustion when probing large proxy pools |
| Package Manager | **npm** | Standard |

> [!NOTE]
> The challenge is evaluated as a **black box**. No database, no Docker requirement mentioned — pure in-memory state with a clean HTTP API is the optimal approach.

---

## Project File Structure

```
proxymaze26/
├── package.json
├── server.js                  # Entry point — starts Express, mounts routes
├── src/
│   ├── config.js              # Runtime config store (check_interval, timeout)
│   ├── proxyStore.js          # Proxy pool: CRUD, status tracking, history
│   ├── monitor.js             # Background monitoring engine (interval loop)
│   ├── alertManager.js        # Alert lifecycle: fire, resolve, re-breach
│   ├── webhookManager.js      # Webhook registry + delivery with retries
│   ├── integrationManager.js  # Slack & Discord integration registry
│   ├── metricsStore.js        # Operational counters
│   └── utils.js               # Helpers: extractProxyId, timestamps
├── routes/
│   ├── health.js              # GET /health
│   ├── config.js              # GET & POST /config
│   ├── proxies.js             # POST, GET, DELETE /proxies; GET /proxies/:id; GET /proxies/:id/history
│   ├── alerts.js              # GET /alerts
│   ├── webhooks.js            # POST /webhooks
│   ├── integrations.js        # POST /integrations
│   └── metrics.js             # GET /metrics
└── tests/
    └── (verification scripts)
```

---

## Data Models

### Config (in-memory singleton)

```js
{
  check_interval_seconds: 30,   // default
  request_timeout_ms: 5000      // default
}
```

### Proxy Object

```js
{
  id: "px-101",                           // extracted from URL path's last segment
  url: "https://proxy-provider.example/proxy/px-101",
  status: "pending" | "up" | "down",
  last_checked_at: null | "ISO8601",      // null until first check
  consecutive_failures: 0,
  total_checks: 0,
  history: [                              // append-only log
    { checked_at: "ISO8601", status: "up" | "down" }
  ]
}
```

**Proxy ID extraction rule:**
```
URL: https://proxy-provider.example/proxy/px-101
                                          ^^^^^^
                                          proxy id = last path segment
```

### Alert Object

```js
{
  alert_id: "alert-<uuid>",       // freshly minted on each breach
  status: "active" | "resolved",
  failure_rate: 0.3,              // rate at fire time
  total_proxies: 10,
  failed_proxies: 3,
  failed_proxy_ids: ["px-103", "px-104", "px-105"],
  threshold: 0.20,
  fired_at: "ISO8601",
  resolved_at: null | "ISO8601",
  message: "Proxy pool failure rate exceeded threshold"
}
```

**Lifecycle state machine:**
```
Normal ──(rate ≥ 0.20)──▶ Active Alert ──(rate < 0.20)──▶ Resolved ──(rate ≥ 0.20)──▶ New Alert
                                                                        │
                                                                        └─ stays in archive
```

### Webhook Registration

```js
{
  webhook_id: "wh-<uuid>",
  url: "https://receiver.example/proxywatch-webhook"
}
```

### Integration Registration

```js
{
  type: "slack" | "discord",
  webhook_url: "https://...",
  username: "ProxyWatch",
  events: ["alert.fired", "alert.resolved"]
}
```

---

## Endpoint Specifications (All 13 Endpoints)

### Chapter 01 — `GET /health` (Proof of Life)

| Aspect | Detail |
|---|---|
| Response | `200 OK` |
| Body | `{ "status": "ok" }` |
| Points | Part of 10pt bootstrap |

---

### Chapter 02 — `POST /config` (The Heartbeat)

| Aspect | Detail |
|---|---|
| Request Body | `{ "check_interval_seconds": N, "request_timeout_ms": N }` |
| Response | `200 OK` with the accepted config |
| Behavior | Must apply **immediately** — restart the monitoring interval |
| Unknown fields | Accept and ignore |

**Implementation:**
1. Validate and store new values in config singleton.
2. Signal the monitor loop to use the new cadence on the next sleep. The loop itself uses `async while(true)` — no interval to clear.

---

### Chapter 03 — `GET /config` (The Memory)

| Aspect | Detail |
|---|---|
| Response | `200 OK`, body = most recently accepted `POST /config` |

---

### Chapter 04 — `POST /proxies` (Building the Pool)

| Aspect | Detail |
|---|---|
| Request Body | `{ "proxies": [...URLs], "replace": true/false }` |
| Response | `201 Created` with `{ accepted: N, proxies: [...] }` |
| `replace: true` | Clear pool first, then load |
| `replace: false/omitted` | Append to current pool |
| Initial status | `"pending"` for all new proxies |
| Unknown fields | Accept and ignore |

**Critical rules:**
- Replacing/clearing pool **must NOT delete previous alerts**.
- After accepting, the monitor picks up new proxies on the next cycle automatically.
- Proxy IDs are **deterministic** from the URL's last path segment.

---

### Chapter 05 — `GET /proxies` (The Watchtower)

| Aspect | Detail |
|---|---|
| Response | `200 OK` |
| Body | `{ total, up, down, failure_rate, proxies: [...] }` |
| `failure_rate` | `down / total` (0 if total is 0) |
| Per-proxy fields | `id, url, status, last_checked_at, consecutive_failures` |

> [!IMPORTANT]
> Values must reflect the **latest background check**, NOT a freshly triggered check. This endpoint is read-only.

---

### Chapter 06 — `GET /proxies/:id` (The Dossier)

| Aspect | Detail |
|---|---|
| Response | `200 OK` or `404 Not Found` |
| Body | All 5 fields from GET /proxies + `total_checks`, `uptime_percentage`, `history` |
| `uptime_percentage` | `(up_checks / total_checks) * 100` |

---

### Chapter 07 — `GET /proxies/:id/history` (The Chronicle)

| Aspect | Detail |
|---|---|
| Response | `200 OK` (JSON array) or `404 Not Found` |
| Body | `[{ checked_at, status }, ...]` |

---

### Chapter 08 — `DELETE /proxies` (The Graveyard)

| Aspect | Detail |
|---|---|
| Response | `204 No Content` |
| Behavior | Clears proxy pool. **Alerts remain accessible.** |

---

### Chapter 09 — `GET /alerts` (The Alert Archive)

| Aspect | Detail |
|---|---|
| Response | `200 OK`, JSON array of all alerts (active + resolved) |
| Required fields | `alert_id, status, failure_rate, total_proxies, failed_proxies, failed_proxy_ids, threshold, fired_at, resolved_at, message` |

---

### Chapter 10 — `POST /webhooks` (The Messenger)

| Aspect | Detail |
|---|---|
| Request | `{ "url": "..." }` (+ ignore unknown fields) |
| Response | `201 Created` with `{ webhook_id, url }` |

**Delivery rules for `alert.fired` and `alert.resolved`:**
- `Content-Type: application/json`
- Deliver within **60 seconds** of state transition
- Retry on **500, 502, 503, 504** until success
- **Exactly one successful delivery** per transition per receiver — no duplicates

---

### Chapter 11 — `POST /integrations` (The Integration Layer)

| Aspect | Detail |
|---|---|
| Request | `{ type: "slack"/"discord", webhook_url, username, events }` |
| Response | `200 OK` or `201 Created` |

---

### Chapter 12 — `GET /metrics` (The Control Room)

| Aspect | Detail |
|---|---|
| Response | `200 OK`, valid non-empty JSON |
| Body | `{ total_checks, current_pool_size, active_alerts, total_alerts, webhook_deliveries }` |

---

## Core Engine Design

### 1. Background Monitor (`src/monitor.js`)

> [!CAUTION]
> **FIX for Issue #1 (setInterval overlap):** Uses `async while(true)` loop, NOT `setInterval`. Each cycle fully completes before the next sleep begins. No overlap possible.

> [!CAUTION]
> **FIX for Issue #2 (Promise.allSettled DOS):** Uses `p-limit` to cap concurrent probes (e.g. 50 at a time). Prevents socket exhaustion on large pools.

> [!CAUTION]
> **FIX for Issue #6 (Pool replacement race):** Takes an **immutable snapshot** of the proxy Map at the start of each cycle. Route handlers can mutate the live Map freely — the running cycle works on a frozen copy.

```
┌──────────────────────────────────────────────────────────────┐
│                  Monitor Loop (async)                         │
│                                                              │
│  while (running) {                                           │
│    const snapshot = [...proxyMap.values()]  // FROZEN COPY   │
│    │                                                         │
│    ├── For each proxy (p-limit concurrency=50):              │
│    │     undici.request(proxy.url, { headersTimeout, ... })  │
│    │       ├── 2xx response → status = "up"                  │
│    │       └── ANYTHING ELSE → status = "down"               │
│    │                                                         │
│    ├── ATOMIC: Update all proxy states at once               │
│    ├── ATOMIC: Compute pool stats + evaluate alerts          │
│    ├── Dispatch webhooks (async, non-blocking)               │
│    └── Increment metrics counters                            │
│                                                              │
│    await sleep(check_interval_seconds * 1000)                │
│  }                                                           │
└──────────────────────────────────────────────────────────────┘
```

**Key design decisions:**

1. **`async while(true)` loop** (Issue #1): Cycle runs → awaits all probes → evaluates alerts → then sleeps for `check_interval_seconds`. Zero overlap risk.
2. **Concurrency-limited probes** (Issue #2): `p-limit(50)` wraps each probe. 10,000 proxies process 50 at a time, not all at once.
3. **`undici` for HTTP probes** (Issue #8): Better timeout semantics, DNS control, and connection pooling than native `fetch`.
4. **Status classification** (Issue #3): **ONLY `2xx` = `up`. Everything else = `down`** (3xx, 4xx, 5xx, timeout, DNS failure, connection refused, etc.).
5. **Immutable pool snapshot** (Issue #6): `const snapshot = [...proxyMap.values()]` at cycle start. Route handlers can `replace` the pool mid-cycle safely.
6. **Atomic state commit** (Issue #12): Compute ALL new states, THEN write them all at once. No intermediate inconsistency visible to GET endpoints.
7. **No check on read:** `GET /proxies` returns cached state from the last completed cycle — never triggers a new check.
8. **Config change handling:** The sleep reads `check_interval_seconds` fresh each iteration. No interval to restart.

> [!WARNING]
> **Issue #3 clarification:** The spec says "2xx ⇒ up, timeout/5xx ⇒ down" but is silent on 3xx/4xx. The **safest** interpretation is: **ONLY 2xx = up. EVERYTHING ELSE = down.** A 404 or 301 proxy is NOT functional.

### 2. Alert Manager (`src/alertManager.js`)

> [!CAUTION]
> **FIX for Issue #4 (Alert mutation):** `failure_rate`, `fired_at`, and `total_proxies` are **FROZEN** at fire time. Only `failed_proxy_ids` and `failed_proxies` are live-updated.

> [!CAUTION]
> **FIX for Issue #12 (State consistency):** Alert evaluation happens atomically as part of the monitor cycle's commit phase. GET endpoints always see a consistent snapshot.

**State machine implementation:**

```js
let activeAlert = null;       // currently active alert (or null)
const alertArchive = [];      // all alerts ever created

function evaluate(pool) {
  const total = pool.length;
  const downProxies = pool.filter(p => p.status === "down");
  const failureRate = total > 0 ? downProxies.length / total : 0;
  const downIds = downProxies.map(p => p.id);

  if (failureRate >= 0.20 && !activeAlert) {
    // FIRE new alert
    activeAlert = {
      alert_id: generateId(),
      status: "active",
      failure_rate: failureRate,    // FROZEN at fire time
      total_proxies: total,        // FROZEN at fire time
      failed_proxies: downProxies.length,  // LIVE — updated each cycle
      failed_proxy_ids: downIds,           // LIVE — updated each cycle
      threshold: 0.20,
      fired_at: nowISO(),          // FROZEN
      resolved_at: null,
      message: "Proxy pool failure rate exceeded threshold"
    };
    alertArchive.push(activeAlert);
    enqueueWebhook("alert.fired", buildFiredPayload(activeAlert));
  }
  else if (failureRate < 0.20 && activeAlert) {
    // RESOLVE current alert
    activeAlert.status = "resolved";
    activeAlert.resolved_at = nowISO();
    activeAlert.failed_proxies = downProxies.length;  // update final count
    activeAlert.failed_proxy_ids = downIds;            // update final set
    enqueueWebhook("alert.resolved", buildResolvedPayload(activeAlert));
    activeAlert = null;
  }
  else if (failureRate >= 0.20 && activeAlert) {
    // UPDATE only LIVE fields — no new webhook
    activeAlert.failed_proxies = downProxies.length;
    activeAlert.failed_proxy_ids = downIds;
    // failure_rate, total_proxies, fired_at remain FROZEN
  }
}
```

**Frozen vs Live fields on active alert:**

| Field | Behavior | Rationale |
|---|---|---|
| `failure_rate` | ❄️ FROZEN at fire time | Spec: "the rate that justified the alert" |
| `total_proxies` | ❄️ FROZEN at fire time | Pool size when alert was created |
| `fired_at` | ❄️ FROZEN | Immutable timestamp |
| `alert_id` | ❄️ FROZEN | Immutable identifier |
| `threshold` | ❄️ FROZEN (always 0.20) | Constant |
| `failed_proxies` | 🔄 LIVE | Must match `failed_proxy_ids.length` |
| `failed_proxy_ids` | 🔄 LIVE | Spec: "IDs of the proxies currently down" |

### 3. Webhook Delivery (`src/webhookManager.js`)

> [!CAUTION]
> **FIX for Issue #5 (Webhook retry duplication):** Uses idempotency keys + in-flight tracking. Each delivery attempt is keyed by `{alert_id}:{event}:{webhook_id}`. If a request succeeds but the response is lost, the retry detects the key is already marked delivered and skips.

> [!CAUTION]
> **FIX for Issue #14 (Infinite retries):** Retry queue is **bounded** (max 100 pending items). Retries cap at **10 attempts** with exponential backoff. After max retries, the delivery is logged as failed and dropped. This prevents unbounded memory growth from dead receivers.

**Architecture:**

```
┌────────────────────────────────────────────────┐
│          Per-Receiver Sequential Queue          │
│                                                │
│  Receiver A:  [fired(a1)] → [resolved(a1)] →   │
│  Receiver B:  [fired(a1)] → [resolved(a1)] →   │
│                                                │
│  Each queue processes ONE event at a time.      │
│  Next event only starts after current succeeds  │
│  or is permanently failed.                      │
└────────────────────────────────────────────────┘
```

**Retry strategy:**

```
Attempt 1 → if 500/502/503/504 → wait 1s
Attempt 2 → wait 2s
Attempt 3 → wait 4s
...
Attempt 10 → GIVE UP (log error, drop from queue)
```

- Exponential backoff: 1s, 2s, 4s, 8s, 16s (capped at 30s per wait)
- **Max 10 retries** per delivery (not infinite)
- **Idempotency key:** `Set<"alertId:event:webhookId">` — once marked delivered, never re-send
- **In-flight tracking:** Before sending, mark as in-flight. On success, mark as delivered. On failure, back to queue.
- **Per-receiver sequential queue:** Events for each receiver are processed in order:
  `alert.fired(alert-1)` → `alert.resolved(alert-1)` → `alert.fired(alert-2)` → ...
- **Bounded queue:** Max 100 pending deliveries per receiver. Oldest dropped if exceeded.

### 4. Integration Delivery (Slack & Discord)

#### Slack Payload (`alert.fired`)

```json
{
  "username": "ProxyWatch",
  "text": "🚨 Proxy pool failure rate exceeded threshold",
  "attachments": [{
    "color": "#FF0000",
    "fields": [
      { "title": "Alert ID", "value": "alert-a1b2c3" },
      { "title": "Failure Rate", "value": "30.0%" },
      { "title": "Failed Proxies", "value": "3 / 10" },
      { "title": "Threshold", "value": "20%" },
      { "title": "Failed IDs", "value": "px-103, px-104, px-105" },
      { "title": "Fired At", "value": "2026-04-24T10:20:00Z" }
    ],
    "footer": "ProxyMaze Alert System",
    "ts": 1745489400
  }]
}
```

**Key constraints:**
- `attachments[0].ts` must be an **integer** (Unix epoch seconds), NOT a float or string
- `attachments[0].color` must be `"#RRGGBB"` hex format
- Field titles must include (case-insensitive): Alert ID, Failure Rate, Failed Proxies, Threshold, Failed IDs, Fired At

#### Slack Payload (`alert.resolved`)

```json
{
  "username": "ProxyWatch",
  "text": "✅ Proxy pool alert resolved",
  "attachments": [{
    "color": "#00FF00",
    "fields": [
      { "title": "Alert ID", "value": "alert-a1b2c3" },
      { "title": "Failure Rate", "value": "..." },
      { "title": "Failed Proxies", "value": "0 / 10" },
      { "title": "Threshold", "value": "20%" },
      { "title": "Failed IDs", "value": "none" },
      { "title": "Fired At", "value": "..." }
    ],
    "footer": "ProxyMaze Alert System",
    "ts": 1745490000
  }]
}
```

#### Discord Payload (`alert.fired`)

```json
{
  "username": "ProxyWatch",
  "embeds": [{
    "title": "🚨 Proxy Alert Fired",
    "description": "Proxy pool failure rate exceeded threshold",
    "color": 16711680,
    "fields": [
      { "name": "Alert ID", "value": "alert-a1b2c3" },
      { "name": "Failure Rate", "value": "30.0%" },
      { "name": "Failed Proxies", "value": "3 / 10" },
      { "name": "Threshold", "value": "20%" },
      { "name": "Failed IDs", "value": "px-103, px-104, px-105" }
    ],
    "footer": { "text": "ProxyMaze Alert System" }
  }]
}
```

**Key constraints:**
- `embeds[0].color` must be an **integer** 0–16777215
- Field names must include (case-insensitive): Alert ID, Failure Rate, Failed Proxies, Threshold, Failed IDs

---

## Behavioral Rules Checklist

These are **non-negotiable** constraints enforced by the black-box evaluator:

- [x] Monitoring runs **continuously in background** via `async while(true)` loop — NOT `setInterval` (Issue #1)
- [x] Proxy status from **real HTTP probes**, never mocked/hardcoded
- [x] **ONLY `2xx` = `up`; EVERYTHING else = `down`** (3xx, 4xx, 5xx, timeout, DNS, connection error) (Issue #3)
- [x] Alert threshold is **0.20** — fires at `≥ 0.20`, resolves at `< 0.20`
- [x] **At most one active alert** at any time
- [x] Continuous breach → same `alert_id`, no duplicate webhooks
- [x] After resolve → fresh breach creates **new `alert_id`**
- [x] Resolved alerts **stay in archive unchanged**
- [x] Webhook event ordering: `fired(old)` → `resolved(old)` → `fired(new)`
- [x] `failed_proxy_ids` always equals **current set of down proxies** (LIVE field)
- [x] `failure_rate` on alert is **FROZEN at fire time** (Issue #4)
- [x] `GET /proxies`, `GET /alerts`, and webhooks **agree exactly** — atomic snapshot commits (Issue #12)
- [x] All JSON request bodies **accept unknown fields** without error
- [x] Proxy IDs are **deterministic** from URL's last path segment
- [x] Same ID appears consistently across all endpoints and payloads
- [x] All timestamps are **ISO 8601 UTC**
- [x] Replacing/clearing pool **does not delete alerts**
- [x] Webhook delivery within **60 seconds**, bounded retries (max 10), idempotency keys (Issues #5, #14)
- [x] Concurrent probes capped via `p-limit(50)` — no socket exhaustion (Issue #2)
- [x] Pool operations use immutable snapshots — no iteration race conditions (Issue #6)
- [x] History arrays capped at 1000 entries per proxy — no memory leak (Issue #7)
- [x] URL validation rejects non-HTTP(S) URLs — no monitor crashes (Issue #9)
- [x] Graceful shutdown on SIGTERM/SIGINT — drain queues before exit (Issue #10)

---

## Proposed Changes

### Core Infrastructure

#### [NEW] [package.json](file:///c:/projects/proxymaze26/proxymaze26/package.json)
- Project metadata, `"type": "module"` for ESM
- Dependencies: `express`, `uuid`, `undici`, `p-limit`
- Scripts: `"start": "node server.js"`, `"dev": "node --watch server.js"`

#### [NEW] [server.js](file:///c:/projects/proxymaze26/proxymaze26/server.js)
- Express app creation, JSON body parsing
- Mount all route modules
- Start HTTP server on configurable port (default 3000)
- Initialize monitor engine
- **Graceful shutdown handler** (Issue #10): `SIGTERM`/`SIGINT` stops monitor loop, drains webhook queue, then exits

---

### Source Modules (`src/`)

#### [NEW] [config.js](file:///c:/projects/proxymaze26/proxymaze26/src/config.js)
- Singleton config store with defaults (`check_interval_seconds: 30`, `request_timeout_ms: 5000`)
- `getConfig()` / `setConfig()` methods
- On `setConfig()`, emit event to trigger monitor restart

#### [NEW] [proxyStore.js](file:///c:/projects/proxymaze26/proxymaze26/src/proxyStore.js)
- `Map<id, ProxyObject>` for the active pool
- `addProxies(urls, replace)` — handles append vs replace logic
- **URL validation** (Issue #9): Reject non-HTTP(S) URLs (`ftp://`, `javascript:`, malformed strings). Use `new URL()` to parse — invalid URLs are silently skipped or return error.
- **Duplicate ID handling** (Issue #13): If two URLs yield the same ID (e.g. `/proxy/px-101` and `/other/px-101`), **last-write-wins** — the later URL overwrites the earlier one. This is the safest default since the spec doesn't define behavior.
- `getAll()`, `getById(id)`, `getHistory(id)`, `clearPool()`
- `updateProxyStatus(id, status, checkedAt)` — updates status, history, consecutive_failures, total_checks
- **Capped history** (Issue #7): History array is a **ring buffer capped at 1000 entries** per proxy. Oldest entries evicted when full. The spec never says "return ALL history" — it says "check history", so a generous cap is safe.
- `getPoolStats()` — returns `{ total, up, down, failure_rate }`
- `getSnapshot()` — returns **frozen array copy** for the monitor to iterate safely (Issue #6)

#### [NEW] [monitor.js](file:///c:/projects/proxymaze26/proxymaze26/src/monitor.js)
- **`async while(true)` loop** — NOT `setInterval` (Issue #1)
- `start()` / `stop()` methods (no `restart` needed — loop reads config fresh each iteration)
- Each cycle: snapshot pool → probe with `p-limit(50)` concurrency → atomic commit → evaluate alerts
- Probe logic: `undici.request(url, { headersTimeout, bodyTimeout })` (Issue #8)
- **Status rule:** `2xx` = `up`, everything else = `down` (Issue #3)
- **Error handling** (Issue #9): Wrap each probe in try/catch — malformed URLs or DNS failures become `down`, not crashes

#### [NEW] [alertManager.js](file:///c:/projects/proxymaze26/proxymaze26/src/alertManager.js)
- `activeAlert` reference + `alertArchive` array
- `evaluate(pool)` — the core state machine (fire/resolve/update)
- `getAlerts()` — returns full archive
- Alert ID generation: `"alert-" + uuid.v4().slice(0,6)` or similar unique scheme

#### [NEW] [webhookManager.js](file:///c:/projects/proxymaze26/proxymaze26/src/webhookManager.js)
- `webhooks` array for registered receivers
- `register(url)` → returns `{ webhook_id, url }`
- `enqueue(event, payload)` — adds to per-receiver sequential queue
- **Bounded retry queue** with exponential backoff, **max 10 attempts** (Issue #14)
- **Idempotency tracking:** `Set<"alertId:event:webhookId">` — prevents duplicate delivery even on response loss (Issue #5)
- **In-flight flag** per delivery to prevent parallel retries of same event

#### [NEW] [integrationManager.js](file:///c:/projects/proxymaze26/proxymaze26/src/integrationManager.js)
- Stores Slack and Discord integration configs
- `formatSlackPayload(event, alert)` — builds Slack attachment structure
- `formatDiscordPayload(event, alert)` — builds Discord embed structure
- Delivery with same retry logic as webhooks

#### [NEW] [metricsStore.js](file:///c:/projects/proxymaze26/proxymaze26/src/metricsStore.js)
- Counters: `total_checks`, `webhook_deliveries`
- Derived: `current_pool_size`, `active_alerts`, `total_alerts`

#### [NEW] [utils.js](file:///c:/projects/proxymaze26/proxymaze26/src/utils.js)
- `extractProxyId(url)` — extracts last path segment
- `nowISO()` — returns current time as ISO 8601 UTC string
- `toUnixEpoch(isoString)` — converts ISO to integer epoch seconds

---

### Route Modules (`routes/`)

#### [NEW] [health.js](file:///c:/projects/proxymaze26/proxymaze26/routes/health.js)
- `GET /health` → `{ status: "ok" }`

#### [NEW] [config.js](file:///c:/projects/proxymaze26/proxymaze26/routes/config.js)
- `POST /config` → store config, restart monitor, return 200
- `GET /config` → return current config, 200

#### [NEW] [proxies.js](file:///c:/projects/proxymaze26/proxymaze26/routes/proxies.js)
- `POST /proxies` → ingest proxies, return 201
- `GET /proxies` → pool summary, 200
- `GET /proxies/:id` → single proxy dossier, 200/404
- `GET /proxies/:id/history` → check history array, 200/404
- `DELETE /proxies` → clear pool, 204

#### [NEW] [alerts.js](file:///c:/projects/proxymaze26/proxymaze26/routes/alerts.js)
- `GET /alerts` → all alerts array, 200

#### [NEW] [webhooks.js](file:///c:/projects/proxymaze26/proxymaze26/routes/webhooks.js)
- `POST /webhooks` → register receiver, 201

#### [NEW] [integrations.js](file:///c:/projects/proxymaze26/proxymaze26/routes/integrations.js)
- `POST /integrations` → register Slack/Discord, 200/201

#### [NEW] [metrics.js](file:///c:/projects/proxymaze26/proxymaze26/routes/metrics.js)
- `GET /metrics` → operational data, 200

---

## Implementation Order

| Phase | Components | Points |
|---|---|---|
| **Phase 1** | `GET /health`, `POST/GET /config` | 10 |
| **Phase 2** | `POST /proxies`, `GET /proxies`, `GET /proxies/:id`, `GET /proxies/:id/history`, `DELETE /proxies` | 45 + 25 |
| **Phase 3** | Background monitor engine | (enables Phase 2 scoring) |
| **Phase 4** | Alert manager + `GET /alerts` | 30 + 90 |
| **Phase 5** | Webhook delivery (`POST /webhooks`) | (part of 90) |
| **Phase 6** | Alert resolution + re-breach lifecycle | 20 + 30 |
| **Phase 7** | `GET /metrics` | (part of 25) |
| **Phase 8** | Slack integration | +10 |
| **Phase 9** | Discord integration | +10 |

---

## Edge Cases & Pitfalls

> [!CAUTION]
> These are the most likely failure points in black-box evaluation. Each is mapped to the issue that identified it.

### Critical (will fail evaluation)

| # | Issue | Edge Case | Fix |
|---|---|---|---|
| 1 | **Monitor overlap** | `setInterval` fires cycle 2 while cycle 1 still running | `async while(true)` loop |
| 2 | **Socket exhaustion** | 10,000 proxies probed simultaneously | `p-limit(50)` concurrency cap |
| 3 | **Wrong status classification** | `404` or `301` proxy classified as `up` | **ONLY `2xx` = `up`** |
| 4 | **Alert field mutation** | `failure_rate` live-updated but spec says "rate that justified the alert" | Freeze `failure_rate`, `total_proxies`, `fired_at` |
| 5 | **Webhook duplicate delivery** | Request succeeds but response lost → retry duplicates | Idempotency key + in-flight tracking |
| 6 | **Pool replacement race** | `POST /proxies replace=true` while monitor iterating | Immutable snapshot at cycle start |
| 12 | **State inconsistency** | Query between proxy update and alert update | Atomic commit of all state |

### Important (may fail evaluation)

| # | Issue | Edge Case | Fix |
|---|---|---|---|
| 7 | **History memory leak** | Millions of history entries over long runs | Ring buffer capped at 1000 per proxy |
| 8 | **`fetch()` limitations** | DNS hangs, weak timeout behavior | Use `undici` with explicit timeouts |
| 9 | **Malformed URLs** | `ftp://`, `javascript:`, invalid strings crash monitor | `new URL()` validation + try/catch in probes |
| 11 | **Pending proxy ambiguity** | Unclear if pending counts in `total` | Literal formula: `down / total`, total = ALL |
| 13 | **Duplicate proxy IDs** | Two URLs yield same ID | Last-write-wins in Map |
| 14 | **Infinite retry queue** | Dead receiver → queue grows forever | Max 10 retries, bounded queue (100) |

### Defensive (good practice)

| # | Issue | Edge Case | Fix |
|---|---|---|---|
| 10 | **No graceful shutdown** | Process killed → retries lost | `SIGTERM`/`SIGINT` handler |
| — | **Empty pool** | `0/0` → `NaN` | Return `0` when `total === 0` |
| — | **`replace: true` + empty array** | Should clear pool | Clear pool, set 0 proxies |
| — | **Pool cleared → active alert** | `0/0 = 0 < 0.20` | Evaluate threshold after pool mutation |
| — | **Unknown JSON fields** | Extra fields must not error | Express `json()` ignores naturally |

---

## Verification Plan

### Automated Tests

```bash
# 1. Start the server
npm start

# 2. Health check
curl http://localhost:3000/health

# 3. Set config
curl -X POST http://localhost:3000/config \
  -H "Content-Type: application/json" \
  -d '{"check_interval_seconds": 5, "request_timeout_ms": 2000}'

# 4. Verify config
curl http://localhost:3000/config

# 5. Load proxies
curl -X POST http://localhost:3000/proxies \
  -H "Content-Type: application/json" \
  -d '{"proxies": ["https://httpbin.org/status/200", "https://httpbin.org/status/500"]}'

# 6. Wait for monitoring cycle, then check pool
sleep 10 && curl http://localhost:3000/proxies

# 7. Check alerts and metrics
curl http://localhost:3000/alerts
curl http://localhost:3000/metrics
```

### Stress & Race Condition Tests

```bash
# Issue #1: Fast interval — verify no duplicate probes
# Issue #2: Load 500 proxies — verify no socket errors
# Issue #6: POST /proxies replace=true while monitor running
# Issue #5: Kill webhook receiver mid-delivery — verify no duplicates
# Issue #12: Query GET /proxies + GET /alerts simultaneously — verify consistency
```

### Behavioral Verification
- Alert lifecycle: fire → resolve → re-fire produces distinct alert_ids
- Webhook deduplication: continuous breach → no duplicate deliveries
- Pool replacement: alerts survive pool clear
- Config change: cadence updates immediately
- `failed_proxy_ids` is live-updated while `failure_rate` stays frozen
- 404/301 proxy URLs classified as `down`

---

## Decisions Made (Previously Open Questions)

> [!NOTE]
> **Failure rate with pending proxies (Issue #11):** Use literal formula `failure_rate = down / total` where `total` = ALL proxies including pending.

> [!NOTE]
> **Status classification (Issue #3):** **ONLY `2xx` = `up`. Everything else = `down`.**

> [!NOTE]
> **Alert field mutation (Issue #4):** `failure_rate` is **frozen** at fire time. `failed_proxy_ids` and `failed_proxies` are **live**.

> [!NOTE]
> **Duplicate proxy IDs (Issue #13):** **Last-write-wins.** Later URL overwrites earlier one.

> [!IMPORTANT]
> **Port configuration:** Defaulting to **3000** with `PORT` env variable support.

> [!NOTE]
> **No persistence needed:** Single-session evaluation. In-memory storage is optimal.


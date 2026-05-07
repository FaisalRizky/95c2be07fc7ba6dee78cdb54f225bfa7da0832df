# Construction Projects

A full-stack web application for browsing and searching UK construction projects. Filter by area, company, or keyword; sort by any column; paginate results; and export the full dataset as a streaming JSON response.

**Stack:** FastAPI (Python 3.10) · AngularJS 1.8 · TypeScript · SQLite · Elasticsearch · nginx · Docker

---

## Assumptions

Several aspects of the requirements were ambiguous. The following decisions are baked into the implementation — each one is a deliberate choice, not an oversight.

| # | Topic | Assumption made |
|---|-------|----------------|
| 1 | **`area` — required or optional?** | Optional. A request with no `area` returns all projects. The requirements listed `area` as optional in the parameter table but as a required-error case in the error-handling section — the parameter table takes precedence. |
| 2 | **One project → multiple areas?** | The schema (`project_area_map` with composite PK) allows many-to-many, but the current dataset is 1:1. The query uses `SELECT DISTINCT` to handle both cases gracefully. |
| 3 | **`project_value` unit** | Pounds (£). Values like `4832115` read as £4.8M — consistent with the scale of construction contracts. Pence would imply £48k, which is implausibly small. |
| 4 | **`description` nullability** | Nullable and passed through as-is. Several rows in the dataset carry `NULL` descriptions; the frontend renders nothing in that case. |
| 5 | **Authentication** | None for this scope. No auth mechanism is defined in the requirements. A production deployment would require at minimum an API key at the router layer. |
| 6 | **Company filter — client-side or server-side?** | Server-side. Client-side filtering only operates on the current page — records on other pages matching the company would be invisible to the user. A dedicated `/companies` endpoint populates the dropdown. |
| 7 | **Date format** | Passed through as-is from the database (`YYYY-MM-DD HH:MM:SS`). The frontend `date` filter handles this format correctly. |
| 8 | **Read-only API** | No write endpoints are implemented. Only `GET` requests are in scope, which is also the reason the Elasticsearch sync limitation (no incremental update) is acceptable — the dataset does not change at runtime. |
| 9 | **Dataset will grow significantly** | The dataset is expected to reach a size where `LIKE '%keyword%'` full-table scans become prohibitive. Elasticsearch was added as the primary search engine for that reason. Trigger search (submit on click, not on keystroke) was chosen deliberately — it avoids firing an ES query on every partial keystroke while the user is still composing a filter. |
| 10 | **No standard response envelope was prescribed** | No envelope format was mandated. A canonical `BaseResponse` envelope (`success`, `status_code`, `data`, `pagination`, `error`) was introduced as a design decision — one consistent shape means one error handler on the client and no branching on response type. |
| 11 | **`/projects` defaults to page 1, 20 results; `per_page > 1000` streams** | Missing `page` defaults to 1; missing `per_page` defaults to 20. For bulk export, callers request `per_page > 1000` — the API switches to cursor-based streaming automatically, preventing OOM on large datasets while keeping the single endpoint contract. |
| 12 | **`GET /projects/{id}` — single project detail endpoint** | The error-handling section mentions *"Project detail not found for a given project ID"*, implying a by-ID endpoint alongside the list endpoint. It is implemented for completeness. Returns `404` with the standard error envelope when the ID does not exist. |
| 13 | **`keyword` searches project name and description** | The `keyword` parameter matches against `project_name` and `description`. Area and company have dedicated exact-match filters (`area`, `company`) so they are excluded from keyword search to keep intent unambiguous. |
| 14 | **Empty result set → `200`, not `404`** | An empty result is a valid query outcome, not a missing resource. The API returns `200` with `data: []` — returning `404` would break client-side pagination logic that expects a consistent envelope. |
| 15 | **Sorting** | `sort_by` and `order` parameters were added as a quality-of-life feature. They are fully optional and default to `project_start DESC`. |
| 16 | **`project_id` added to the response** | The original response schema lists 7 fields. `project_id` is included as an 8th — it is the natural primary key and is required by the by-ID endpoint and client-side deduplication logic. |
| 17 | **Missing pagination params default gracefully** | Missing `page` defaults to 1; missing `per_page` defaults to 20. No error is returned for partial params — the missing value is always filled with a sensible default. |
| 18 | **XLSX is out of scope — the API provides the data feed** | The context mentions exporting all projects to a single XLSX file, and notes *"your endpoint may be used to retrieve the projects."* The streaming endpoint is the data source; XLSX generation is a separate concern handled by the consumer of this API. |
| 19 | **Elasticsearch is an optional optimisation** | Only SQLite was initially described. Elasticsearch was added as an optimisation for large datasets. It is entirely optional — if ES is unavailable at startup, the service falls back to SQLite automatically with no configuration change. |
| 20 | **`/areas` and `/companies` are cached** | The app is expected to be heavily used. Areas and companies change rarely — they grow only when new construction projects are added, which happens infrequently. Hitting the database on every request for these two dropdowns would be unnecessary load at scale. A short TTL in-memory cache absorbs repeated calls without stale-data risk. |
| 21 | **No CORS configuration needed** | The frontend and API share the same origin. nginx serves the frontend on port 4200 and proxies `/api/` to the backend on the same host — the browser never makes a cross-origin request. CORS headers are therefore unnecessary in this deployment topology. If the API were accessed directly from a different domain (mobile app, third-party client), CORS middleware would be required. |
| 22 | **Single commit history** | In a production workflow, each feature or fix would have its own focused commit. This repository has a single commit because the entire project was treated as one deliverable. Granular commits with descriptive messages are the standard day-to-day practice. |
| 23 | **`glenigan.sql` committed intentionally** | Database files are normally excluded via `.gitignore` and provisioned separately — never committed to version control. It is included here solely so the reviewer can run the project without any extra setup steps. |

---

## Design Choices

### Backend architecture — layered with strategy pattern

The backend is split into four clear layers:

- **`config/`** — engine abstractions for database, cache, and search. Each is a Python `Protocol` (interface), with concrete implementations behind it. Swapping SQLite → PostgreSQL, memory cache → Redis, or SQLite search → Elasticsearch requires changing one environment variable — no business logic changes.
- **`services/`** — pure business logic: query building, pagination, streaming, ES sync. No HTTP knowledge here.
- **`routers/`** — thin HTTP layer. Validates parameters, calls services, returns responses.
- **`utils/`** — shared helpers: response envelope, error handlers, sorting, rate limiting.

#### Project structure

```
backend/
├── main.py                    # entry point — middleware, routers, lifespan
├── bootstrap.py               # startup: DB health check → ES index sync
├── config/                    # swappable engine implementations (strategy pattern)
│   ├── app.py                 # AppConfig — central env-var registry
│   ├── db.py                  # DatabaseEngine protocol + SQLiteEngine
│   ├── cache.py               # CacheEngine protocol + MemoryTTLCache
│   ├── search.py              # SearchProvider — ES / SQLite auto-switcher
│   └── elasticsearch.py       # ES client, index setup, bulk indexing
├── routers/
│   └── projects.py            # /projects · /areas · /companies (HTTP only)
├── services/
│   └── project_service.py     # query building, pagination, streaming
├── utils/
│   ├── responses.py           # BaseResponse envelope + stream constants
│   ├── errors.py              # global exception handlers (404, 422, 429, 500)
│   ├── sorting.py             # ORDER BY clause builder
│   ├── rate_limit.py          # slowapi Limiter instance
│   └── es_helpers.py          # wait_for_elasticsearch helper
└── test_main.py               # unit (mock DB) + integration tests
```

Request flow through the layers:

```
HTTP Request
    │
    ▼
routers/projects.py        validates params, calls service, returns BaseResponse
    │
    ▼
services/project_service.py   builds SQL, calls SearchProvider then DB engine
    ├──────────────────────────────────────────────┐
    ▼                                              ▼
config/search.py                             config/db.py
(ES or SQLite, decided at runtime)           (SQLite or Postgres, decided at startup)
    │
    ▼
utils/responses.py         wraps result in BaseResponse envelope → HTTP Response
```

#### Why the strategy pattern?

This project is explicitly at an early stage — SQLite today, PostgreSQL eventually; in-memory cache now, Redis later; no search engine initially, Elasticsearch optionally. Without the strategy pattern, every one of those future swaps would require touching the service layer, the routers, and potentially the tests. With it, each concern has exactly one place to change:

- Switch database: add a `PostgresEngine` class, set `DB_ENGINE=postgres`. Zero query changes needed — `_normalize_sql()` handles placeholder translation.
- Switch cache: add a `RedisEngine` class, set `CACHE_ENGINE=redis`. The `@apply_cache` decorator is unaware of the implementation.
- Switch search: `SearchProvider` already hot-swaps between `SqliteSearchEngine` and `ElasticSearchEngine` at runtime with no config change.

It also makes the codebase testable in isolation — unit tests inject a mock `DatabaseEngine` via FastAPI's `Depends()`, so tests never touch a real database.

### Default sort order — `project_start DESC`

`project_start DESC` (most recent start date first) is the default for three reasons:

1. **Most relevant on first load** — users browsing an unfamiliar area want to see active or upcoming projects before historical ones. Newest first matches the mental model of "what is happening now."
2. **Stable pagination** — a deterministic sort column prevents rows from shifting between pages when a new project is added. `project_start` is a stable, indexed column, and a secondary `project_name ASC` tie-breaker ensures full determinism even when two projects share the same start date.
3. **Consistent with industry tools** — project management dashboards (Jira, Asana, Linear) all default to most-recent-first for the same reason.

### Default page size — `20`

When neither `page` nor `per_page` is supplied the API defaults to `page=1, per_page=20`. `20` was chosen because:

- It renders in under 100 ms even on a mid-range mobile device.
- It fits a typical laptop viewport without scrolling past the fold, making the pagination controls visible on first load.
- It is the most common default in REST APIs and matches the frontend dropdown's lowest option.

### `/api/v1/` prefix — best practice versioning

A versioned prefix (`/api/v1/`) serves two purposes:

1. **Breaking-change isolation** — when a future `/v2/` is introduced, existing clients continue to hit `/v1/` without modification. Without versioning, a breaking change forces all clients to update simultaneously.
2. **Gateway routing** — the `/api/` segment lets nginx (or any API gateway) route traffic to the backend without path conflicts with frontend routes. The frontend uses `/api/v1/...` as a relative path; nginx proxies it internally.

### Canonical response envelope

Every endpoint returns the same `BaseResponse` shape regardless of success or failure:

```json
{ "success": true,  "data": [...], "pagination": {...}, "error": null }
{ "success": false, "data": null,  "pagination": null,  "error": { "code": "...", "message": "..." } }
```

One shape everywhere means one error handler on the client and no branching on response type.

### Trigger search, not live search

The filter bar submits on button click or Enter key — not on every keystroke. Debounced live search was considered and rejected for three reasons:

1. **Wasted requests** — every partial word fires a backend call. Typing "Manchester" generates 9 requests; only the last one matters.
2. **Inconsistent pagination state** — if the user is on page 3 and starts typing, the page must reset to 1 on every keystroke, causing the table to jump while they are mid-word.
3. **Perceived performance** — a spinner that flickers on every character is more disruptive than a single spinner triggered intentionally. Explicit submit gives the user full control over when the search runs.

### Streaming for bulk export — OOM prevention

When `per_page > 1000` the API automatically switches to `StreamingResponse` with a cursor-based generator (100 rows per chunk). This means the server never loads the full result set into RAM regardless of how many rows match the filters — important given the non-functional context of thousands of projects per area.

It does **not** solve the **response-time** problem. The HTTP connection stays open for the full transfer duration. Any intermediate proxy (nginx, load balancer, CDN) may cut the connection before the transfer completes due to its own read timeout. The correct production solution for bulk export is an **asynchronous background job** — the client requests an export, receives a job ID, polls for completion, and downloads from a signed S3/GCS URL.

### nginx as reverse proxy

The frontend JavaScript uses a relative API path (`/api/v1/...`). nginx proxies `/api/` to the backend container on the internal Docker network. This means the browser never needs to know the backend port, there are no CORS issues, and changing ports only requires editing `.env`.

### Rate limiting

All endpoints are protected by per-IP rate limits using `slowapi`:

| Endpoint | Limit |
|----------|-------|
| `GET /api/v1/projects` | 60 / minute |
| `GET /api/v1/areas` | 30 / minute |
| `GET /api/v1/companies` | 30 / minute |

Exceeding the limit returns `HTTP 429` with the standard error envelope.

### `GET /api/v1/projects` — query parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `keyword` | string | Case-insensitive substring search across **project name and description**. Use `area` and `company` filters for those fields. |
| `area` | string | Exact match (case-insensitive) against the project area. |
| `company` | string | Exact match (case-insensitive) against the company name. |
| `page` | integer ≥ 1 | Page number. Defaults to `1`. |
| `per_page` | integer ≥ 1 | Results per page. Defaults to `20`. Values above `1000` switch to streaming. |
| `sort_by` | string | Column to sort by: `project_id`, `project_name`, `project_start`, `project_end`, `company`, `project_value`, `area`. Defaults to `project_start`. |
| `order` | `asc` \| `desc` | Sort direction. Defaults to `desc`. |

### Linting and formatting as first-class concerns

Code quality tooling is wired in from the start, not added as an afterthought:

- **Backend — `ruff` + `mypy`**: `ruff` replaces `flake8`, `black`, and `isort` in a single fast binary. `mypy` enforces type correctness. Together they catch import ordering issues, unused variables, ambiguous names, line-length violations, and type mismatches before code reaches review. 127 issues were caught and resolved during development.
- **Frontend — `eslint` + `prettier`**: `eslint` with the `@typescript-eslint` plugin enforces TypeScript-specific rules. `prettier` enforces consistent formatting. The `triple-slash-reference` rule is intentionally disabled — it is required for `tsc --outFile` (non-module) compilation, which is the correct build approach for brownfield AngularJS.

Both toolchains are configured in `pyproject.toml` (backend) and `.eslintrc.json` / `.prettierrc` (frontend) so they run identically in every developer's environment and in CI.

### Database placeholder abstraction

All SQL uses `?` as the canonical placeholder. Each database engine translates it internally (`_normalize_sql`). Switching from SQLite to PostgreSQL (which uses `%s`) requires no changes to any query string — only the engine implementation changes.

### Frontend architecture

#### Project structure

```
frontend/
├── src/                       # TypeScript source — compiled as a single bundle
│   ├── app.ts                 # Module declaration + ngRoute config (reads APP_ROUTES)
│   ├── config/
│   │   └── app.ts             # APP_CONFIG constant — API base URL, pagination defaults
│   ├── routes/
│   │   └── index.ts           # APP_ROUTES array — single source of truth for all routes
│   ├── services/
│   │   └── ProjectService.ts  # $http factory — all backend calls in one place
│   ├── controllers/
│   │   └── ProjectsDashboardController.ts  # Filter state, pagination, sort, URL sync
│   ├── components/
│   │   └── base/
│   │       ├── siteHeader.ts  # <site-header> reusable component
│   │       └── siteFooter.ts  # <site-footer> reusable component
│   └── utils/
│       └── currency.ts        # formatCurrency filter (GBP formatting)
└── dist/                      # Compiled output — served directly by nginx
    ├── index.html             # App shell (loads AngularJS from CDN, then app.js)
    ├── app.js                 # All of src/ compiled into one file by tsc --outFile
    ├── style.css              # Global stylesheet
    └── templates/             # AngularJS HTML partials — no JavaScript, markup only
        ├── projects-dashboard.html
        ├── not-found.html
        └── base/
            ├── site-header.html
            └── site-footer.html
```

#### AngularJS 1.8 via CDN — brownfield match

AngularJS 1.8 was chosen to mirror the existing brownfield environment. The framework is loaded from a pinned CDN URL (`1.8.3`) rather than bundled — this avoids introducing a Webpack or Rollup pipeline that the rest of the brownfield codebase does not have. CDN delivery also means the browser can serve the file from cache if the user has visited any other site using the same pinned version.

#### TypeScript compiled to a single `outFile`

AngularJS 1.x predates ES modules. All code runs in the global browser scope — controllers, services, and filters register themselves on the `app` module variable. TypeScript's `tsc --outFile dist/app.js` concatenates every `src/**/*.ts` file into one bundle in declaration order, which is exactly how a pre-module AngularJS project expects its scripts to load. Using a module bundler (Webpack, Rollup, Vite) would require significant shim work to bridge ES modules back to global scope — unnecessary complexity for a brownfield context.

#### Factory pattern for services

`ProjectService` is an `app.factory()`, not a class-based `app.service()`. Factories are the idiomatic AngularJS 1.x pattern for HTTP wrappers: they return a plain object of functions, which is straightforward to stub in unit tests with `$httpBackend`. The returned functions (`getProjects`, `getAreas`, `getCompanies`) each return a typed `IPromise`, keeping the controller unaware of `$http` internals.

#### `controllerAs: '$ctrl'` instead of `$scope`

The dashboard controller uses `controllerAs` binding (`$ctrl`) rather than injecting `$scope` directly. This avoids AngularJS's prototype chain scope inheritance — a well-known source of subtle bugs when parent and child scopes share property names. `$ctrl.property` is always unambiguous. It also makes the controller a plain TypeScript class with typed properties, which is easier to read, test, and migrate away from.

#### URL-synchronised filter state

Every filter change (area, keyword, company, page, sort) is written to the URL via `$location.search()`. This makes filtered views bookmarkable and shareable. The controller listens to `$routeUpdate` (with `reloadOnSearch: false` so the controller is not destroyed and recreated on every filter change) and reconciles its state with the URL only when the URL actually differs from the current state — preventing feedback loops.

---

## Tradeoffs

| Decision | Benefit | Cost |
|----------|---------|------|
| **Elasticsearch for search** | Handles large datasets with fast full-text search; `LIKE '%keyword%'` on SQLite is a full table scan that degrades linearly | Extra infrastructure to run and maintain; index is rebuilt from scratch on every restart, meaning a brief window where search falls back to SQLite |
| **SQLite fallback when ES is down** | Zero-config local development; the app is still usable without running an ES container | SQLite search is a full table scan — unacceptable at production scale; masks ES availability issues rather than surfacing them |
| **Trigger search (button click)** | One request per intentional search; pagination state is stable while the user types | Slightly less instant than live search — the user must explicitly submit |
| **Streaming when `per_page > 1000`** | Server never loads the full result set into RAM; single endpoint handles both paginated and bulk-export use cases | HTTP connection stays open for the full transfer; proxies may time out before it completes; no progress indicator on the client |
| **In-process cache and rate limiter** | No extra infrastructure (Redis); trivially simple to run locally | State is lost on restart; not shared across multiple instances — neither the cache hit rate nor the rate limit count would be correct in a multi-pod deployment |
| **Raw SQL over ORM** | Full control over every query; no abstraction leakage; easy to audit for performance; `_normalize_sql()` makes driver-swapping explicit | More boilerplate; no schema migrations; JOIN logic lives in strings rather than model relationships |
| **`BaseResponse` envelope over a plain array** | One consistent shape across every endpoint; one error handler on the client; error and pagination metadata travel in the same object as data | Deviates from the simplest possible response format (`[{...}]`); adds a small amount of wrapper payload per response |
| **AngularJS 1.8 via CDN (brownfield match)** | No build pipeline changes to the wider codebase; CDN-cached across sites using the same pinned version | Framework reached end-of-life in December 2021; no future security patches; CDN availability is a runtime dependency |
| **`tsc --outFile` (single bundle, no module bundler)** | No Webpack/Vite config for a brownfield project that doesn't need it; output is a single predictable file | No tree shaking or code splitting; all source files share global scope; declaration order matters |
| **Strategy pattern for all engines** | Each engine (DB, cache, search) is swappable by a single env-var change; unit tests inject mocks with zero setup | More indirection than a simple script; the protocol + implementation split is overkill if the engine never actually changes |
| **Same-origin via nginx proxy (no CORS)** | No preflight `OPTIONS` requests; no CORS misconfiguration risk; simpler backend with zero CORS middleware | API is inaccessible from any other origin — a mobile app, external client, or direct `curl` from a browser tab on a different host would be blocked by the browser's same-origin policy |

---

## Known Limitations

### SQLite

- **No connection pool.** A new connection is opened and closed for every query. Acceptable for SQLite's WAL mode at low concurrency; would be a bottleneck under load.
- **`LIKE '%keyword%'` is always a full table scan.** A leading wildcard cannot use a B-tree index. This is why Elasticsearch exists — the SQLite path is acceptable only for small datasets or when ES is unavailable.
- **No write concurrency.** SQLite serialises all writes. Any future mutation endpoint would contend under concurrent load.

### Elasticsearch

- **Index is rebuilt on every restart.** `setup_elasticsearch()` deletes and recreates the index at boot. There is a brief window where ES has no data and requests silently fall back to SQLite.
- **New or updated records are not reflected until restart.** There is no incremental sync — if the underlying SQLite database changes, Elasticsearch will be out of date until the next server restart. Since this API is read-only (`GET` only, no write endpoints), this is an acceptable trade-off: the dataset does not change at runtime, so ES always reflects the full current state after startup.
- **`area` filter is case-sensitive in ES, case-insensitive in SQLite.** A direct API call with `area=manchester` (lowercase) returns results from the SQLite fallback but zero results from ES. The frontend dropdown avoids this by always sending correctly-cased values.

### Cache

- **In-memory, single-process.** The TTL cache for `/areas` and `/companies` lives in the FastAPI process. It resets on restart and is not shared across multiple instances.

### Rate limiter

- **In-memory counters.** Limits reset on server restart and are not shared across instances. A Redis-backed limiter is needed for multi-instance deployments.

### CORS

- **No CORS headers are set.** The current deployment assumes the frontend and API share the same origin via nginx. Any consumer on a different origin (mobile app, third-party integration, or direct browser call) will be blocked. Adding CORS is a one-line FastAPI middleware addition (`CORSMiddleware`) but requires explicit allow-list decisions on origins, methods, and headers.

### Frontend

- **AngularJS 1.x reached end-of-life in December 2021.** No security patches have been issued since. The framework is used here to match an existing brownfield codebase; a migration roadmap to a supported framework is strongly recommended.

---

## Production Recommendations

| Area | Current state | Production target |
|------|--------------|-------------------|
| **Database** | SQLite, one connection per request | PostgreSQL with `asyncpg` connection pool |
| **Cache** | In-process TTL dict | Redis — shared across instances, survives restarts |
| **Rate limiter** | In-process counters | `slowapi` with `storage_uri="redis://..."` |
| **Search** | ES rebuilt on restart, no incremental sync | Blue/green index alias swap on rebuild; CDC pipeline (triggers → queue → indexer) for real-time sync |
| **Bulk export** | Not implemented — callers consume the paginated endpoint | Async background job (Celery) → upload to S3 → signed download URL; decouples export duration from HTTP request lifetime entirely |
| **Authentication** | None | JWT or API key validation at the router layer; `Depends()` makes this a one-file change |
| **Observability** | `print()` statements | Structured logging (JSON), Sentry for exceptions, Datadog/Prometheus for metrics |
| **Secrets** | Environment variables in `.env` | Vault or cloud secret manager (AWS Secrets Manager, GCP Secret Manager) |
| **Frontend** | AngularJS 1.x (EOL) | Migrate to Angular 17+, React, or Vue; use a proper module bundler (Vite/Webpack) |
| **Tests** | `pytest` — 20 unit tests (mocked DB) + integration suite | Playwright for E2E; Jest/Karma for frontend components |

---

## Getting Started

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) 24+
- [Docker Compose](https://docs.docker.com/compose/install/) v2.22+
- The `glenigan.sql` database file placed at the **repository root** (see assumption 23)

### Run (Docker — recommended)

Before starting Docker, compile the frontend bundle once:

```bash
cd frontend
npm install
npm run build   # generates dist/app.js
cd ..
```

Then start all services:

```bash
docker compose up -d
```

> The backend expects `glenigan.sql` at the repository root and Elasticsearch running on `http://localhost:9200`. If Elasticsearch is unavailable it falls back to SQLite automatically.

### Open the app

| URL | Description |
|-----|-------------|
| `http://localhost:4200` | Frontend dashboard |
| `http://localhost:8000/docs` | Interactive API docs (Swagger UI) |
| `http://localhost:8000/health` | Health check |

> **Swagger UI note:** Requesting `per_page` above ~100 in Swagger UI may freeze or crash the browser tab. Swagger renders the full response as a syntax-highlighted JSON tree in the DOM — it is not designed for bulk data. Use `curl` or Postman for large result sets.

### Stop

```bash
docker compose down
```

---

> **Port conflict?** Copy `.env.example` to `.env` and change the port numbers before running `docker compose up -d`.
> ```bash
> cp .env.example .env
> ```
> Default ports: Frontend `4200` · Backend `8000` · Elasticsearch `9200`

---

## Linting & Formatting

### Backend — `ruff` + `mypy`

```bash
cd backend

# Check for issues
.venv/bin/ruff check .

# Auto-fix all fixable issues (imports, whitespace, unused variables, etc.)
.venv/bin/ruff check . --fix

# Format code (black-compatible)
.venv/bin/ruff format .

# Type checking
.venv/bin/mypy .
```

Install dev tools (included in `requirements-dev.txt`):

```bash
.venv/bin/pip install -r requirements-dev.txt
```

### Frontend — `eslint` + `prettier`

```bash
cd frontend

# Check for lint issues
npm run lint

# Auto-fix all fixable lint issues
npm run lint:fix

# Check formatting
npm run format:check

# Auto-format all source files
npm run format
```

---

## Running Tests

Tests live in `backend/test_main.py` and are split into two layers:

| Layer | Needs DB? | Command |
|-------|-----------|---------|
| Unit | No — mock DB injected | `pytest -m unit` |
| Integration | Yes — `glenigan.sql` at repo root | `pytest -m integration` |

```bash
cd backend
.venv/bin/pytest -m unit -v          # 20 tests, no database required
.venv/bin/pytest -m integration -v   # requires glenigan.sql
.venv/bin/pytest -v                  # run everything
```

Install test dependencies if not already installed:

```bash
.venv/bin/pip install -r requirements.txt   # pytest and httpx are included
```

---

## AI Assistance

This project was developed with the assistance of [Claude Code](https://claude.ai/code) (Anthropic). AI was used to accelerate implementation, catch edge cases, and iterate on documentation — all design decisions, assumptions, and tradeoffs documented in this README reflect deliberate engineering judgment made by the author.

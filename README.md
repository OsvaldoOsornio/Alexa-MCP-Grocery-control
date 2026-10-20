# Eat Me First

[![CI](https://github.com/OsvaldoOsornio/Alexa-MCP-Grocery-control/actions/workflows/ci.yml/badge.svg)](https://github.com/OsvaldoOsornio/Alexa-MCP-Grocery-control/actions/workflows/ci.yml)

**An Alexa+ kitchen agent that knows what is about to go bad — and tells you what to cook with it.**

Built for the Build, Ship, Shape: Amazon Developer Hackathon, **Alexa+ track**, using a self-hosted **MCP server** that implements specification **2025-11-25 over Streamable HTTP**, with **Amazon Bedrock** for multimodal receipt extraction and adaptive recipe reasoning.

Nobody decides to throw food away. You cannot see the back of your own fridge, you do not remember which day you opened the yogurt, and the moment you decide what to cook is never the moment you think about what is expiring. Eat Me First closes that gap: photograph a receipt, and the pantry ages itself from then on.

## How it uses Alexa+

Everything the product does runs through a self-hosted **MCP server** that **Alexa+** connects to. This is not a REST API with an MCP label on it:

- The server negotiates a real protocol session and issues an `Mcp-Session-Id` header.
- It advertises JSON-Schema-typed tools through `tools/list`.
- It returns `structuredContent` from `tools/call`.
- It speaks **MCP specification 2025-11-25** over **Streamable HTTP**, verified against a live server.

Because the pantry lives in PostgreSQL rather than in a chat transcript, **Alexa+** gets state that persists across sessions.

None of that is a claim you have to take on trust. With the server running, `python scripts/mcp_smoke.py` drives it with the **official MCP Python SDK client** and prints the negotiated protocol version, the `Mcp-Session-Id`, the advertised tool schemas and two live `tools/call` results. To connect your own MCP-capable client instead, paste [`docs/mcp-client-config.json`](docs/mcp-client-config.json) into its configuration. Both are covered in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#verify-it-with-a-real-mcp-client-in-two-minutes).

| Tool | Purpose | Key arguments |
|---|---|---|
| `get_inventory_status` | Read rows from `v_pantry_inventory_status` | `user_id`, optional `include_consumed` |
| `modify_item_state` | Mark opened or consumed, or change location | `user_id`, `item_id`, `is_opened`, `opened_date`, `storage_location`, `is_consumed` |
| `ingest_receipt_items` | Extract products from a photo and insert them | `user_id`, `image_base64`, optional `media_type` |
| `update_pantry_context` | Adjust shelf life from spoken observation | `user_id`, `item_name`, `modifier` |
| `generate_and_adapt_recipe` | Build or re-plan a recipe around what expires soonest | `user_id`, `servings`, `exclude_items`, `prior_recipe` |

Two of these make it an agent rather than a CRUD wrapper. `update_pantry_context` takes what a person says out loud -- "the avocados are very ripe" -- and rewrites the item's shelf life. `generate_and_adapt_recipe` reads the pantry ordered by urgency and asks Bedrock for a dish built around it, then re-plans mid-cook when an ingredient runs out.

## How it uses Amazon Bedrock

`ingest_receipt_items` sends the receipt image to **Amazon Bedrock** through the **Converse API** with Claude Opus 4.5, using `boto3`. The reply is parsed as strict JSON and validated by a Pydantic model with `extra="forbid"` before anything reaches the database. Extracted ingredients are matched against the `shelf_life_rules` catalog; unmatched items are stored as free items in the pantry.

The receipt never decides the expiry date. PostgreSQL does.

`generate_and_adapt_recipe` is the second **Amazon Bedrock** call, and a different kind of call. The first extracts; this one reasons. It receives the inventory ordered by `days_remaining` and must build a dish from it, constrained to pantry items plus a short list of assumed staples -- anything else it wants is reported in a `missing` field rather than silently invented. Passing a `prior_recipe` together with `exclude_items` switches it from generate to adapt, which is how a mid-cook re-plan happens in one round trip.

## Architecture

```mermaid
flowchart LR
	U[Person] --> UI[Next.js React UI]
	UI --> RP[Next.js Route Handler /api/mcp]
	RP --> MCP[FastMCP · Streamable HTTP · 2025-11-25]
	MCP --> TOOLS[Five MCP tools]
	TOOLS --> SVC[Python services]
	SVC --> ORM[SQLAlchemy async]
	ORM --> PG[(PostgreSQL)]
	PG --> TR[Status view and expiry trigger]
	SVC --> BOTO[boto3 · Converse]
	BOTO --> BEDROCK[Amazon Bedrock · Claude Opus 4.5]
	BEDROCK --> SVC
```

The browser never connects directly to PostgreSQL, AWS or the MCP endpoint. It asks the Next.js Route Handler, which negotiates a server-to-server MCP session.

**Expiry is owned by the database.** A trigger computes `expiration_date` on every insert and update, in this priority order: a user-set `custom_expiration_date`; the frozen shelf life when the item is in the freezer; the opened date times the opened multiplier; otherwise purchase date plus unopened shelf life. The UI and the agent read that result and never recompute it, so they cannot disagree.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for module-level detail and the full tool payload contracts.

## Requirements

- Python 3.10 or later
- Node.js 24 LTS and npm
- Docker, for the bundled PostgreSQL — or your own PostgreSQL reachable via `DATABASE_URL`
- AWS credentials with Amazon Bedrock model access, to process real receipts

## Run it locally

### 1. Start PostgreSQL

```powershell
docker compose up -d
```

That is the whole step. `docker-compose.yml` runs `postgres:17` and applies `database/schema.sql`, `database/seed_shelf_life_rules.sql` and `database/seed_demo_user.sql` on first boot, so the database comes up with the ENUMs, the expiry trigger, the shelf-life catalog and the `user_id = 1` the frontend and the examples assume. Credentials match the `DATABASE_URL` default, so nothing needs editing.

The init scripts only run when the data volume is empty. After changing a `.sql` file, run `docker compose down -v` to discard the volume and let them re-apply.

Without Docker, create the database by hand instead:

```powershell
createdb zero_waste_sous_chef
psql -d zero_waste_sous_chef -f database/schema.sql
psql -d zero_waste_sous_chef -f database/seed_shelf_life_rules.sql
psql -d zero_waste_sous_chef -f database/seed_demo_user.sql
```

`database/schema.sql` is the source of truth for the ENUMs, tables, view and trigger. Do not replace the trigger by computing `expiration_date` in Python or React.

### 2. Start the MCP server

From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
python -m app.main
```

The server listens on `http://127.0.0.1:8000/mcp` by default.

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Async SQLAlchemy connection; use `postgresql+asyncpg://...` |
| `AWS_REGION` | Bedrock region |
| `BEDROCK_MODEL_ID` | Bedrock inference profile ID; Claude Opus 4.5 by default |
| `MCP_SERVER_HOST`, `MCP_SERVER_PORT` | Streamable HTTP host and port |
| `MCP_SERVER_NAME` | Name announced by FastMCP |

AWS uses the standard boto3 credential chain, for example a local profile or an execution role. Never put keys in the repository.

### 3. Start the frontend

In another terminal:

```powershell
Set-Location frontend
npm ci
Copy-Item .env.example .env.local
npm run dev
```

Open `http://localhost:3000`. The frontend also runs without a backend, showing clearly labelled demo data.

## Tests

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

`requirements.txt` holds only what the server needs at runtime; `requirements-dev.txt` adds it plus pytest and the `psycopg` driver.

Model, service and MCP protocol tests need neither AWS nor PostgreSQL. The PostgreSQL trigger tests — the only ones that cover the expiry calculation — skip unless `TEST_DATABASE_URL` is set. With the bundled database running:

```powershell
$env:TEST_DATABASE_URL = "postgresql+psycopg://postgres:changeme@localhost:5432/zero_waste_sous_chef"
python -m pytest -q
```

Note the `+psycopg` driver: the tests connect synchronously, while the application uses `+asyncpg`.

## Continuous integration

[`.github/workflows/ci.yml`](.github/workflows/ci.yml) runs on every push and pull request:

- **Python** — `pytest -q` against a `postgres:17` service container, with `database/schema.sql` and both seeds applied and `TEST_DATABASE_URL` set, so the trigger tests execute rather than skip. A final step fails the job if they were skipped anyway, because a green run that quietly skipped them would read as coverage that is not there.
- **Frontend** — `npm ci`, `npm run lint`, `npm test` and `npm run build` on Node 24.

From `frontend/`:

```powershell
npm run lint
npm test
npm run build
```

## Inventory traffic light

| MCP status | CSS class | Meaning |
|---|---|---|
| `fresh` | `status-fresh` | In good condition |
| `expiring_soon` | `status-expiring_soon` | Expiring shortly |
| `expired` | `status-expired` | Past its date |
| `consumed` | `status-consumed` | Consumed |
| `unknown` | `status-unknown` | No computable date |

`quantity` arrives as a decimal serialized to text, dates as ISO 8601. When `expiration_date` is `null` the UI shows `unknown` rather than inventing an estimate.

## Security and known limits

- **The MCP server does not authenticate callers.** `user_id` is a tool argument, not a verified identity. Do not expose this server to an untrusted network without adding authentication and authorization.
- The server binds to `127.0.0.1` by default. The MCP SDK automatically enables DNS rebinding protection for loopback hosts, so Host headers other than `127.0.0.1`, `localhost` and `[::1]` are rejected with HTTP 421. Changing the bind address to `0.0.0.0` silently disables that protection.
- Processing real receipts requires Bedrock permissions and can incur AWS costs. Demo mode calls neither Bedrock nor the database.
- Receipt text flows into a Bedrock prompt. The blast radius is limited: the response model forbids extra fields and caps lengths, and `ingredient_name` is matched against the catalog rather than trusted.
- The database ships a `users` stub. Adjust its key and the relationships before integrating a real identity provider.
- `npm audit` reports 5 high-severity advisories, all of them the same `braces` denial-of-service reached through one dev-only chain: `eslint-config-next` -> `@next/eslint-plugin-next` -> `fast-glob` -> `micromatch` -> `braces`. Nothing in `app/`, `components/` or `lib/` imports it, so it never enters the production bundle and is not reachable at runtime; it runs only when you run `npm run lint`. `npm audit fix --force` 'fixes' this by installing `eslint-config-next@14.2.35`, two major versions below the `next@16.4.0` in use, which breaks the setup. The advisories are therefore accepted deliberately, not overlooked, and clear when upstream ships a patched `fast-glob`.

## License

MIT. See [LICENSE](LICENSE).

## Contributing

1. Open an issue describing the change or the problem.
2. Send a small pull request with tests and updated documentation.
3. Run the checks for the area you touched: `pytest -q` for Python; `npm run lint`, `npm test` and `npm run build` for the frontend.
4. Never commit `.env`, credentials, personal data or real receipts.

## Documentation

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — modules, MCP transport and tool payload contracts
- [docs/VISION.md](docs/VISION.md) — the product this is becoming
- [database/README.md](database/README.md) — entity relationships and the expiry logic

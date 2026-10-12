# Eat Me First — kitchen UI

React/Next.js interface for simulating kitchen events and reading the inventory traffic light.

## Start

From this directory:

```powershell
npm install
npm run dev
```

Open `http://localhost:3000`. The demo inventory and local events are enabled automatically when the MCP server does not respond.

## Connect the backend

Copy `.env.example` to `.env.local` and adjust `MCP_URL` if the MCP server is not at `http://127.0.0.1:8000/mcp`. The `/api/mcp` Route Handler negotiates a Streamable HTTP session and calls only the allow-listed tools. The interface uses `get_inventory_status`, `modify_item_state` and `ingest_receipt_items`.

The frontend defaults to `user_id: 1`, a demonstration identifier. The backend does not authenticate the user yet, so this value does not constitute authorization.

## Demo mode

When the backend is unreachable the UI falls back to local sample data, labelled `Demo mode` in the header and with a ribbon along the bottom. Demo changes are not persisted and never reach Bedrock or PostgreSQL.

The demo dates are pinned to a fixed origin so that server and client render identically; they drift from the real "today" over time. Record demonstrations with the backend running and the `MCP live` badge showing.

## Checks

```powershell
npm run lint
npm test
npm run build
```

`npm test` uses Vitest, JSDOM and React Testing Library.

`npm audit` reports advisories in `eslint-config-next` → `fast-glob` → `micromatch` → `braces`. These are development-only dependencies and do not reach the production bundle. Do not run `npm audit fix --force`: it downgrades `eslint-config-next` to v14 and breaks the Next 16 setup.

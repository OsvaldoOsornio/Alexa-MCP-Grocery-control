# Context pack

Working notes for anyone (human or agent) picking up this project. Everything
here was verified by running it, not read off the source.

## 1. Product

Eat Me First is an Alexa+ kitchen agent that tracks what is in your pantry,
knows what is about to go bad, and builds a recipe around it. Intake is a
photograph of a grocery receipt, so nobody has to type their shopping in.

**Target user.** Households that cook most nights and shop weekly, where food
gets thrown out on autopilot. Kitchen-first, hands busy, eyes on the pan.

**Problem.** Nobody decides to throw food away. You cannot see the back of
your own fridge, you do not remember when you opened the yogurt, and the
moment you choose what to cook is never the moment you think about what is
expiring.

## 2. Stack and how to run it

| Layer | Technology |
|---|---|
| MCP server | Python, FastMCP, Streamable HTTP, spec 2025-11-25, SDK 1.30.0 |
| AI | Amazon Bedrock Converse via boto3 |
| Database | PostgreSQL 17 in Docker; expiry owned by a trigger |
| Frontend | Next.js 16, React 19, TypeScript, Tailwind 4 |

Verified run sequence:

```bash
docker compose up -d                       # Postgres, schema + seeds auto-applied
python -m app.main                         # MCP server on 127.0.0.1:8000/mcp
cd frontend && npm run dev                 # UI on localhost:3000
```

Checks: `pytest -q` is 87 passed / 3 skipped, or **90 passed / 0 skipped**
with `TEST_DATABASE_URL` set. Frontend `npm run lint`, `npm test`,
`npm run build` all pass.

Credentials split, which is non-obvious: AWS keys go in `~/.aws/credentials`
because boto3 reads its own chain, while `AWS_REGION` and `BEDROCK_MODEL_ID`
go in `.env` because `app/services/bedrock.py` passes region explicitly.
Nothing calls `load_dotenv`, so AWS keys in `.env` are silently ignored.

## 3. Where the track tech is called at runtime

| What | File:line | Evidence |
|---|---|---|
| MCP server built | `app/main.py:11-29` `build_server()` | — |
| Streamable HTTP transport | `app/main.py:37` `mcp.run(transport="streamable-http")` | live `initialize` returns `protocolVersion 2025-11-25` + `Mcp-Session-Id` |
| Tool registration | `app/tools/inventory.py:15`, `app/tools/recipe.py:13` | `tools/list` returns 5 tools |
| Bedrock client | `app/services/bedrock.py:28-31` `boto3.client("bedrock-runtime")` | — |
| Bedrock extract | `app/services/inventory.py:54-106` `client.converse(...)` | 12 items extracted from a real receipt photo |
| Bedrock reason | `app/services/recipe.py:130-141` `client.converse(...)` | returned "Roasted Tomato Soup" from the live pantry |

All five tools verified over a real MCP SDK client against live PostgreSQL
and live Bedrock.

## 4. The demo path

1. **Ambient screen** — Echo Show frame at 1280x800 shows the pantry with a
   traffic light. Badge reads `MCP live`; data comes from PostgreSQL.
2. **Ask what is going bad** — `get_inventory_status` returns rows whose
   status the database computed, not the app.
3. **Speak context** — "the tomatoes are very ripe" fires
   `update_pantry_context`; the card flips state in place.
4. **Photograph a receipt** — `ingest_receipt_items` sends the image to
   Bedrock, which returns structured line items that are validated and
   inserted.
5. **Ask what is for dinner** — `generate_and_adapt_recipe` builds a dish
   around the soonest-expiring item.
6. **Run out of something** — same tool with `prior_recipe` plus
   `exclude_items` re-plans live.

## 5. Image upload flow

**It exists and works.** Verified with a real 164 KB receipt photograph.

- **Starts at** the developer bench below the device frame
  (`frontend/components/dev-bench.tsx`), Receipt mode. The bench is
  deliberately outside the Echo Show frame and labelled a developer control,
  because a file picker is not something an Echo Show has.
- **Browser** reads the file with `FileReader`, strips the data URL prefix,
  keeps base64 only.
- **Endpoint** `POST /api/mcp` (`frontend/app/api/mcp/route.ts`), a
  server-side proxy with a five-tool allow-list. The browser never sees the
  MCP endpoint, the database or AWS.
- **Transport** `frontend/lib/mcp-client.ts` opens a Streamable HTTP session
  and calls `tools/call`.
- **Processing** `app/services/inventory.py` validates type and size, calls
  Bedrock Converse with the image, validates the reply against a Pydantic
  model with `extra="forbid"`, matches names against `shelf_life_rules`,
  inserts rows. PostgreSQL computes expiry.
- **Limits** JPEG, PNG, GIF, WebP; 5 MB decoded maximum.
- **After upload** the user sees the voice transcript strip name the tool,
  then the new cards appear with expiry dates the trigger assigned.
- **Honest failure** no AWS credentials produces a real error state, never a
  stubbed recipe or invented date.

## 6. Screens

One route. The product is a single ambient surface, not an app with
navigation.

| Route | What |
|---|---|
| `/` | Echo Show frame 1280x800: voice transcript strip, four item cards, ambient headline, recipe stage. Developer bench sits outside the frame. |
| `/api/mcp` | Server-side MCP proxy, POST only, tool allow-list |

## 7. Known risks

| Risk | State |
|---|---|
| **Repo is private** | 404s to judges. Fails the submission requirement outright. Unfixed. |
| **One unpushed commit** | `a6c8c49`, the Bedrock model fix. GitHub still advertises an end-of-life model ID. |
| **`main` is 22 commits behind** | Default branch is still the original Spanish project. |
| Committed default model is Opus | `.env` overrides with Sonnet 4.5. They disagree. |
| No video | Hard requirement, does not exist yet. |
| Demo data ages | Dates are relative to purchase, so the traffic light drifts. Refresh before filming. |
| Catalog is 15 English ingredients | A non-English or restaurant receipt matches nothing and renders grey. Use a supermarket receipt for the demo. |
| No authentication | `user_id` is a tool argument, not an identity. Disclosed honestly in the README. |

No secrets in the repo or in git history; verified by scanning all 23,044
lines of `git log -p --all`.

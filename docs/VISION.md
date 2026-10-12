# Vision

What Eat Me First is becoming, and which parts of it exist today.

## The product

A conversational and visual agent, running on **Alexa+** and rendered on an Echo Show, that manages kitchen inventory, tracks how long food actually has left, and adapts recipes in real time.

It attacks food waste by removing the friction of manual data entry: computer vision for intake, voice for context, and a database that ages the pantry on its own.

The system proactively surfaces ingredients close to expiring, suggests recipes that make the most of what is already in the kitchen, and adjusts a preparation mid-cook when something runs out.

## Why voice, and why a screen

The moment that decides whether food gets eaten or thrown away is the moment someone opens the fridge with their hands full. That is not a moment for a phone app. It is a moment for asking out loud and glancing at a screen, which is exactly the interaction model Alexa+ on an Echo Show provides.

## Status

| Capability | Tool | State |
|---|---|---|
| Read the pantry and its expiry status | `get_inventory_status` | **Built** |
| Mark opened, consumed, or moved | `modify_item_state` | **Built** |
| Receipt photo to inventory, via Bedrock | `ingest_receipt_items` | **Built** |
| Voice context that changes shelf life | `update_pantry_context` | Planned |
| Generate and adapt a recipe | `generate_and_adapt_recipe` | Planned |
| Amazon Fresh order sync | `sync_amazon_fresh_delivery` | Not scheduled |

### Voice context

`update_pantry_context(item_name, modifier)` adjusts shelf life from what the person observes. Saying the avocados are very ripe closes the consumption window to roughly 24 hours.

This is cheap to build because the database already supports it: the expiry trigger honours `custom_expiration_date` above every other branch, so writing that single column overrides the whole rules engine.

### Adaptive chef

`generate_and_adapt_recipe` designs a recipe that prioritises the soonest-expiring ingredients, then recalculates steps and proportions live when an ingredient is missing or is swapped for something closer to its date.

Two modes share one tool: generate, when no prior recipe is supplied; and adapt, when a prior recipe plus excluded items are. The second is what makes a mid-cook re-plan demonstrable.

## Principles

1. **The database owns time.** Expiry is computed by a PostgreSQL trigger, never in Python or React, so the voice channel and the screen cannot disagree.
2. **Never invent a date.** An item with no computable expiry reports `unknown`. An estimate presented as a fact destroys trust in the traffic light.
3. **Never invent an ingredient.** A generated recipe may only use what is in the inventory plus a short list of assumed staples. Anything else is reported as missing.
4. **Intake must cost nothing.** Every pantry app that asks people to type in their groceries dies at that step.
5. **Demo mode must be unmistakable.** Local sample data is always labelled as such and never presented as persistence.

## Stack

- **MCP server:** Python with FastMCP, Streamable HTTP, specification 2025-11-25
- **Database:** PostgreSQL — `shelf_life_rules` as the master expiry catalog, `pantry_inventory` as live stock with a trigger-computed expiry
- **AI:** Amazon Bedrock for multimodal extraction and adaptive reasoning
- **Frontend:** React and Next.js, as an Echo Show surface plus a developer event simulator

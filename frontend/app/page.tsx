"use client";

import { CloudOff, CookingPot, RotateCw, X } from "lucide-react";
import { useEffect, useState } from "react";
import { DevBench, type StateAction } from "@/components/dev-bench";
import { ItemCard, RestOfKitchenCard } from "@/components/item-card";
import { RecipeStage, type RecipeView } from "@/components/recipe-stage";
import { VoiceTranscript } from "@/components/voice-transcript";
import {
  byUrgency, createDemoInventory, createDemoReceiptItems, DEMO_USER_ID,
  formatDate, initialDemoEvents, locationLabel, needsAttention,
  RIPENESS_UTTERANCES,
  type DemoEvent, type InventoryItem, type InventoryStatusResponse,
  type McpToolName, type PantryContextResponse, type RecipeResponse,
  type RipenessModifier, type StorageLocation, type VoiceTurn,
} from "@/lib/kitchen-data";

type ConnectionState = "checking" | "demo" | "live";

// The Echo Show frame shows at most four cards. Four is what fits at a size
// that reads from two metres, and an ambient screen is not a list.
const CARD_SLOTS = 4;

// The exchange the page opens with. Constant, so it renders identically on the
// server and the client, and the strip is already showing the real tool name
// while that first call is still in flight.
const OPENING_TURN: VoiceTurn = {
  id: 1,
  utterance: "Alexa, what needs eating?",
  tool: "get_inventory_status",
  reply: "",
  state: "working",
};

async function invokeTool<T>(tool: McpToolName, args: Record<string, unknown>): Promise<T> {
  const response = await fetch("/api/mcp", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tool, arguments: args }),
  });
  const payload = (await response.json()) as { data?: T; error?: string };
  if (!response.ok || payload.data === undefined) {
    throw new Error(payload.error ?? "Could not connect to MCP.");
  }
  return payload.data;
}

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const dataUrl = String(reader.result ?? "");
      const comma = dataUrl.indexOf(",");
      if (comma < 0) reject(new Error("Could not read the image."));
      else resolve(dataUrl.slice(comma + 1));
    };
    reader.onerror = () => reject(new Error("Could not read the image."));
    reader.readAsDataURL(file);
  });
}

function todayIso(): string {
  const date = new Date();
  const offset = date.getTimezoneOffset();
  return new Date(date.getTime() - offset * 60_000).toISOString().slice(0, 10);
}

/** How a voice assistant would read the attention count back out loud. */
function spokenAttention(items: InventoryItem[]): string {
  const urgent = items.filter(needsAttention).sort(byUrgency);
  if (!urgent.length) return "Nothing needs eating today. The pantry is fine.";
  // Verbatim: lower-casing a display name turns "Whole milk 1L" into
  // "whole milk 1l", which is worse spoken aloud than the odd capital.
  const names = urgent.slice(0, 2).map((item) => item.display_name).join(" and ");
  if (urgent.length === 1) return `One thing needs eating: ${names}.`;
  return urgent.length > 2
    ? `${urgent.length} things need eating, starting with ${names}.`
    : `${urgent.length} things need eating: ${names}.`;
}

export default function Home() {
  const [items, setItems] = useState<InventoryItem[]>(createDemoInventory);
  const [events, setEvents] = useState<DemoEvent[]>(initialDemoEvents);
  const [connection, setConnection] = useState<ConnectionState>("checking");
  const [turn, setTurn] = useState<VoiceTurn>(OPENING_TURN);
  const [isWorking, setIsWorking] = useState(false);
  const [toast, setToast] = useState("");
  const [recipeView, setRecipeView] = useState<RecipeView | null>(null);
  const [recipeStep, setRecipeStep] = useState(0);

  // Opens the exchange with the question the device is actually for. The tool
  // name in the strip is the one this call is issued with, and the reply is
  // read off the rows PostgreSQL returned.
  useEffect(() => {
    let active = true;
    invokeTool<InventoryStatusResponse>("get_inventory_status", {
      user_id: DEMO_USER_ID, include_consumed: true,
    }).then((data) => {
      if (!active || !Array.isArray(data.items)) return;
      setItems(data.items);
      setConnection("live");
      setTurn({ ...OPENING_TURN, reply: spokenAttention(data.items), state: "answered" });
    }).catch((error: unknown) => {
      if (!active) return;
      setConnection("demo");
      setTurn({
        ...OPENING_TURN,
        reply: error instanceof Error ? error.message : "The MCP server did not answer.",
        state: "failed",
      });
    });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(""), 3600);
    return () => window.clearTimeout(timer);
  }, [toast]);

  const activeItems = items.filter((item) => item.status !== "consumed");
  const attentionItems = activeItems.filter(needsAttention).sort(byUrgency);
  const freshCount = activeItems.filter((item) => item.status === "fresh").length;
  const ranked = [...activeItems].sort(byUrgency);
  const shown = ranked.length > CARD_SLOTS ? ranked.slice(0, CARD_SLOTS - 1) : ranked;
  const hidden = ranked.length - shown.length;

  function announce(title: string, detail: string, kind: DemoEvent["kind"]) {
    setEvents((current) => [{
      id: Date.now(), title, detail,
      time: new Intl.DateTimeFormat("en", { hour: "2-digit", minute: "2-digit" })
        .format(new Date()),
      kind,
    }, ...current].slice(0, 6));
  }

  function beginTurn(utterance: string, tool: McpToolName) {
    setTurn({ id: Date.now(), utterance, tool, reply: "", state: "working" });
  }

  function finishTurn(reply: string, state: VoiceTurn["state"]) {
    setTurn((current) => ({ ...current, reply, state }));
  }

  async function refreshInventory(): Promise<InventoryItem[]> {
    const data = await invokeTool<InventoryStatusResponse>("get_inventory_status", {
      user_id: DEMO_USER_ID, include_consumed: true,
    });
    if (!Array.isArray(data.items)) throw new Error("The inventory received is not valid.");
    setItems(data.items);
    setConnection("live");
    return data.items;
  }

  async function retryConnection() {
    setConnection("checking");
    beginTurn("Alexa, read the pantry again.", "get_inventory_status");
    try {
      const fresh = await refreshInventory();
      finishTurn(spokenAttention(fresh), "answered");
      setToast("Inventory connection restored.");
    } catch (error) {
      setConnection("demo");
      finishTurn(
        error instanceof Error ? error.message : "The MCP server did not answer.",
        "failed",
      );
      setToast("Backend unavailable. Still in demo mode.");
    }
  }

  async function handleReceipt(file: File) {
    setIsWorking(true);
    beginTurn("Alexa, add this shop from the receipt.", "ingest_receipt_items");
    try {
      const imageBase64 = await fileToBase64(file);
      if (connection === "live") {
        const result = await invokeTool<{ success: boolean; count: number }>(
          "ingest_receipt_items",
          { user_id: DEMO_USER_ID, image_base64: imageBase64, media_type: file.type },
        );
        if (!result.success) throw new Error("The receipt could not be processed.");
        await refreshInventory();
        announce("Receipt processed", `${result.count} products added from the photo`, "receipt");
        finishTurn(`Added ${result.count} items from that receipt.`, "answered");
        setToast(`${result.count} products added to the inventory.`);
        return;
      }
      const newItems = createDemoReceiptItems(Date.now());
      setItems((current) => [...newItems, ...current]);
      announce("Receipt simulated", "2 products added in demo mode", "receipt");
      finishTurn("Added 2 items. Demo data, because MCP is not connected.", "answered");
      setToast("Receipt simulated. 2 sample products were added.");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Could not read the photo.";
      finishTurn(message, "failed");
      setToast(message);
    } finally {
      setIsWorking(false);
    }
  }

  async function handleStateEvent(
    itemId: number, action: StateAction, location: StorageLocation,
  ) {
    const item = items.find((entry) => entry.id === itemId);
    if (!item) {
      setToast("There are no items to modify.");
      return;
    }

    setIsWorking(true);
    const spoken = action === "open"
      ? `Alexa, I opened the ${item.display_name}.`
      : action === "consume"
        ? `Alexa, we finished the ${item.display_name}.`
        : `Alexa, I moved the ${item.display_name} to the ${locationLabel(location).toLocaleLowerCase("en")}.`;
    beginTurn(spoken, "modify_item_state");

    const actionLabel = action === "open"
      ? "Item marked as opened"
      : action === "consume"
        ? "Item marked as consumed"
        : `Item moved to the ${locationLabel(location).toLocaleLowerCase("en")}`;
    const kind: DemoEvent["kind"] =
      action === "open" ? "opened" : action === "consume" ? "consumed" : "moved";

    try {
      if (connection === "live") {
        const args: Record<string, unknown> = { user_id: DEMO_USER_ID, item_id: itemId };
        if (action === "open") {
          args.is_opened = true;
          args.opened_date = todayIso();
        } else if (action === "consume") {
          args.is_consumed = true;
        } else {
          args.storage_location = location;
        }
        const result = await invokeTool<{ success: boolean; error?: string }>(
          "modify_item_state", args,
        );
        if (!result.success) throw new Error(result.error ?? "Could not update.");
        const fresh = await refreshInventory();
        announce(actionLabel, `${item.display_name} · now`, kind);
        finishTurn(`Got it. ${spokenAttention(fresh)}`, "answered");
        setToast("Event applied to the inventory.");
        return;
      }

      setItems((current) => current.map((entry) => {
        if (entry.id !== itemId) return entry;
        if (action === "open") return { ...entry, is_opened: true };
        if (action === "consume") {
          return { ...entry, status: "consumed" as const, quantity: "0.00" };
        }
        return { ...entry, storage_location: location };
      }));
      announce(actionLabel, `${item.display_name} · now`, kind);
      finishTurn("Noted locally. MCP is not connected, so nothing was written.", "answered");
      setToast("Event applied in the local simulator.");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Could not apply the event.";
      finishTurn(message, "failed");
      setToast(message);
    } finally {
      setIsWorking(false);
    }
  }

  async function handleContextEvent(itemName: string, modifier: RipenessModifier) {
    setIsWorking(true);
    beginTurn(RIPENESS_UTTERANCES[modifier](itemName), "update_pantry_context");
    try {
      if (connection !== "live") {
        finishTurn(
          "I cannot change a shelf life without the database. MCP is not connected.",
          "failed",
        );
        setToast("Spoken context needs a live MCP connection.");
        return;
      }
      const result = await invokeTool<PantryContextResponse>("update_pantry_context", {
        user_id: DEMO_USER_ID, item_name: itemName, modifier,
      });
      // The tool answers ambiguity with candidate names rather than guessing,
      // so the honest reply is the follow-up question, not an error.
      if (!result.success || !result.item) {
        const candidates = result.candidates ?? [];
        finishTurn(
          candidates.length
            ? `Which one did you mean: ${candidates.join(", ")}?`
            : result.error ?? "I could not find that in your pantry.",
          "failed",
        );
        setToast(result.error ?? "No matching item.");
        return;
      }

      const { display_name, expiration_date, days_remaining, discard_recommended } = result.item;
      await refreshInventory();
      announce(
        "Shelf life rewritten",
        `${display_name} · now ${formatDate(expiration_date)}`,
        "opened",
      );
      finishTurn(
        discard_recommended
          ? `Then throw the ${display_name} out. I have marked that as gone off today.`
          : `Noted. I have moved the ${display_name} to ${formatDate(expiration_date)}, ${
            days_remaining === 1 ? "1 day" : `${days_remaining} days`} from now.`,
        "answered",
      );
      setToast(`${display_name} now expires ${formatDate(expiration_date)}.`);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Could not apply the context.";
      finishTurn(message, "failed");
      setToast(message);
    } finally {
      setIsWorking(false);
    }
  }

  async function handleRecipe(servings: number) {
    setIsWorking(true);
    setRecipeStep(0);
    setRecipeView({ state: "working", error: "", recipe: null, expiringInPantry: [] });
    beginTurn("Alexa, what can I cook tonight?", "generate_and_adapt_recipe");
    try {
      if (connection !== "live") {
        throw new Error("The MCP server is not connected, so there is no pantry to cook from.");
      }
      const result = await invokeTool<RecipeResponse>("generate_and_adapt_recipe", {
        user_id: DEMO_USER_ID, servings,
      });
      if (!result.success || !result.recipe) {
        throw new Error(result.error ?? "The recipe tool returned no recipe.");
      }
      setRecipeView({
        state: "ready", error: "", recipe: result.recipe,
        expiringInPantry: result.expiring_soon_in_pantry ?? [],
      });
      const rescued = result.recipe.uses_expiring;
      finishTurn(
        rescued.length
          ? `${result.recipe.title}, ${result.recipe.total_minutes} minutes. It uses ${rescued.join(" and ")}.`
          : `${result.recipe.title}, ${result.recipe.total_minutes} minutes.`,
        "answered",
      );
      announce("Recipe generated", result.recipe.title, "receipt");
    } catch (error) {
      // No fallback recipe. A plausible-looking dish here would be the one
      // thing on this screen that is not real, and the whole project rests on
      // demo data being labelled as demo data.
      const message = error instanceof Error
        ? error.message
        : "The recipe tool could not be reached.";
      setRecipeView({ state: "failed", error: message, recipe: null, expiringInPantry: [] });
      finishTurn(message, "failed");
    } finally {
      setIsWorking(false);
    }
  }

  return (
    <main className="bench">
      <div className="device-shell">
        <div className="device-screen">
          {recipeView ? (
            <RecipeStage
              view={recipeView} step={recipeStep}
              onStep={setRecipeStep} onClose={() => setRecipeView(null)}
            />
          ) : null}
          <VoiceTranscript turn={turn} />

          <section className="ambient" aria-label="Items needing attention">
            <p className="ambient-count">
              <strong>{attentionItems.length}</strong>
              <span>
                {attentionItems.length === 1
                  ? "item needs eating"
                  : "items need eating"}
                <small>
                  {freshCount} {freshCount === 1 ? "other item is" : "others are"} still fresh
                </small>
              </span>
            </p>
            <span className={`device-badge badge-${connection}`}>
              <span className="badge-light" />
              {connection === "live" ? "MCP live" : connection === "checking" ? "Connecting" : "Demo mode"}
            </span>
          </section>

          <section className="card-grid" aria-label="Pantry" aria-live="polite">
            {shown.map((item) => <ItemCard item={item} key={item.id} />)}
            {shown.length < CARD_SLOTS
              ? <RestOfKitchenCard hidden={hidden} tracked={ranked.length} />
              : null}
          </section>

          <footer className="device-foot">
            <span className="device-brand">
              <CookingPot size={17} strokeWidth={2.3} /> eat me first
            </span>
            <span className="device-source">
              {connection === "live"
                ? "Expiry dates computed in PostgreSQL"
                : "Demo data · not from the database"}
            </span>
            <button
              className="device-sync" onClick={retryConnection}
              disabled={connection === "checking"}
            >
              <RotateCw size={15} />
              {connection === "live" ? "Re-read" : "Retry"}
            </button>
          </footer>
        </div>
      </div>

      <p className="frame-note">
        Echo Show 15 viewport, 1280 &times; 800. The wording of each utterance is
        scripted; the tool call and the spoken reply behind it are real.
      </p>

      <DevBench
        items={items} events={events} isWorking={isWorking}
        onReceipt={handleReceipt} onStateEvent={handleStateEvent}
        onContextEvent={handleContextEvent} onRecipe={handleRecipe}
      />

      {connection === "demo" && (
        <div className="demo-ribbon">
          <CloudOff size={13} /> Backend disconnected &middot; local demo changes
        </div>
      )}
      {toast && (
        <div className="toast-message" role="status">
          {toast}
          <button onClick={() => setToast("")} title="Close notice" aria-label="Close notice">
            <X size={14} />
          </button>
        </div>
      )}
    </main>
  );
}

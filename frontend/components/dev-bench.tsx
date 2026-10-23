"use client";

import {
  ArrowRight, Check, ChevronDown, CircleCheck, LoaderCircle, ScanLine,
  CookingPot, MessageSquareQuote, Settings2, Snowflake, Sparkles, Terminal,
  Upload, X,
} from "lucide-react";
import Image from "next/image";
import { useRef, useState, type ChangeEvent } from "react";
import {
  RIPENESS_UTTERANCES,
  type DemoEvent, type InventoryItem, type Recipe, type RipenessModifier,
  type StorageLocation,
} from "@/lib/kitchen-data";

export type StateAction = "open" | "consume" | "move";
type BenchMode = "receipt" | "state" | "context" | "recipe";

function EventMark({ kind }: { kind: DemoEvent["kind"] }) {
  if (kind === "receipt") return <ScanLine size={15} />;
  if (kind === "opened") return <Sparkles size={15} />;
  if (kind === "consumed") return <CircleCheck size={15} />;
  return <Snowflake size={15} />;
}

type DevBenchProps = {
  items: InventoryItem[];
  events: DemoEvent[];
  isWorking: boolean;
  onReceipt(file: File): void;
  onStateEvent(itemId: number, action: StateAction, location: StorageLocation): void;
  onContextEvent(itemName: string, modifier: RipenessModifier): void;
  onRecipe(servings: number): void;
  // The recipe currently on the device screen, or null when the stage is
  // closed. The "ran out" control can only offer what the dish actually uses.
  recipe: Recipe | null;
  onRanOut(ingredient: string): void;
};

/**
 * The developer bench: deliberately outside the device frame.
 *
 * An Echo Show has no file picker and no dropdowns, so none of this can sit on
 * the simulated screen without lying about the product. It lives below the
 * frame as what it is -- the control that fires voice events during a demo,
 * standing in for the microphone this machine does not have.
 *
 * It keeps its own form state. The page only receives the action to perform.
 */
export function DevBench({
  items, events, isWorking, onReceipt, onStateEvent, onContextEvent, onRecipe,
  recipe, onRanOut,
}: DevBenchProps) {
  const [mode, setMode] = useState<BenchMode>("receipt");
  const [stateAction, setStateAction] = useState<StateAction>("open");
  const [moveLocation, setMoveLocation] = useState<StorageLocation>("freezer");
  const [modifier, setModifier] = useState<RipenessModifier>("underripe");
  const [servings, setServings] = useState(2);
  const [selectedItemId, setSelectedItemId] = useState<number | null>(null);
  const [ranOutItem, setRanOutItem] = useState<string | null>(null);
  const [receiptFile, setReceiptFile] = useState<File | null>(null);
  const [receiptPreview, setReceiptPreview] = useState("");
  const [benchNote, setBenchNote] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const actionable = items.filter((item) => item.status !== "consumed");
  // Falls back to the first actionable item so the bench is usable the moment
  // live data arrives, without an effect that fights the user's own choice.
  const targetId = actionable.some((item) => item.id === selectedItemId)
    ? (selectedItemId as number)
    : (actionable[0]?.id ?? null);
  const target = actionable.find((item) => item.id === targetId);

  // Only a pantry ingredient can run out in a way the tool can act on. The
  // rest are the staples it already assumes, so excluding one tells it
  // nothing about the pantry.
  const pantryIngredients = (recipe?.ingredients ?? []).filter(
    (ingredient) => ingredient.from_pantry,
  );
  // Defaults away from the items the dish was built to rescue -- excluding one
  // of those is the least interesting thing to demonstrate.
  const rescued = recipe?.uses_expiring ?? [];
  const defaultRanOut =
    pantryIngredients.find((one) => /whole milk/i.test(one.name))?.name
    ?? pantryIngredients.find((one) => /milk/i.test(one.name))?.name
    ?? pantryIngredients.find((one) => !rescued.includes(one.name))?.name
    ?? pantryIngredients[0]?.name
    ?? "";
  // Same fallback shape as `targetId`: the user's own choice wins while it is
  // still in the list, without an effect that fights it.
  const ranOutTarget = pantryIngredients.some((one) => one.name === ranOutItem)
    ? (ranOutItem as string)
    : defaultRanOut;

  function onFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    if (!["image/jpeg", "image/png", "image/gif", "image/webp"].includes(file.type)) {
      setBenchNote("Use a JPEG, PNG, GIF or WebP image.");
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      setBenchNote("The photo must be 5 MB or less.");
      return;
    }
    if (receiptPreview) URL.revokeObjectURL(receiptPreview);
    setBenchNote("");
    setReceiptFile(file);
    setReceiptPreview(URL.createObjectURL(file));
  }

  function clearReceipt() {
    if (receiptPreview) URL.revokeObjectURL(receiptPreview);
    setReceiptPreview("");
    setReceiptFile(null);
  }

  return (
    <section className="dev-bench" aria-label="Developer control">
      <header className="bench-head">
        <span className="bench-tag">
          <Terminal size={14} /> Developer control
        </span>
        <p>
          Not part of the product. This machine has no microphone, so these
          buttons stand in for a spoken request and fire the same MCP tool the
          voice intent would. Every call they make shows up in the transcript on
          the screen above, under its real tool name.
        </p>
      </header>

      <div className="bench-body">
        <div className="bench-controls">
          <div className="bench-switch" role="tablist" aria-label="Event type">
            <button
              role="tab" aria-selected={mode === "receipt"}
              className={mode === "receipt" ? "bench-tab selected" : "bench-tab"}
              onClick={() => setMode("receipt")}
            >
              <ScanLine size={15} /> Receipt photo
            </button>
            <button
              role="tab" aria-selected={mode === "state"}
              className={mode === "state" ? "bench-tab selected" : "bench-tab"}
              onClick={() => setMode("state")}
            >
              <Settings2 size={15} /> Item state
            </button>
            <button
              role="tab" aria-selected={mode === "context"}
              className={mode === "context" ? "bench-tab selected" : "bench-tab"}
              onClick={() => setMode("context")}
            >
              <MessageSquareQuote size={15} /> Spoken context
            </button>
            <button
              role="tab" aria-selected={mode === "recipe"}
              className={mode === "recipe" ? "bench-tab selected" : "bench-tab"}
              onClick={() => setMode("recipe")}
            >
              <CookingPot size={15} /> Cook
            </button>
          </div>

          {mode === "receipt" ? (
            <div className="bench-form">
              <p className="bench-hint">
                Sends the photo to <code>ingest_receipt_items</code>, which reads
                it with Bedrock and writes the lines it finds to PostgreSQL.
              </p>
              <input
                ref={fileInputRef} className="visually-hidden" type="file"
                aria-hidden="true" tabIndex={-1}
                accept="image/jpeg,image/png,image/gif,image/webp"
                onChange={onFileChange}
              />
              {receiptPreview ? (
                <div className="bench-preview">
                  <Image
                    src={receiptPreview} alt="Receipt preview"
                    width={420} height={150} unoptimized
                  />
                  <button
                    className="bench-preview-clear" onClick={clearReceipt}
                    title="Remove photo" aria-label="Remove photo"
                  >
                    <X size={14} />
                  </button>
                </div>
              ) : null}
              <button
                className="bench-choose" onClick={() => fileInputRef.current?.click()}
              >
                <Upload size={14} />
                {receiptFile ? receiptFile.name : "Choose a receipt image"}
              </button>
              <button
                className="bench-fire" disabled={isWorking || !receiptFile}
                onClick={() => { if (receiptFile) onReceipt(receiptFile); }}
              >
                {isWorking ? <LoaderCircle className="spin" size={15} /> : <Sparkles size={15} />}
                {isWorking ? "Calling the tool" : "Fire the receipt event"}
                {!isWorking && <ArrowRight size={15} />}
              </button>
            </div>
          ) : mode === "state" ? (
            <div className="bench-form">
              <p className="bench-hint">
                Sends <code>modify_item_state</code>, the tool behind
                &ldquo;Alexa, I opened the milk&rdquo;.
              </p>
              <label className="bench-label" htmlFor="bench-item">Item</label>
              <div className="bench-select">
                <select
                  id="bench-item" value={targetId ?? ""}
                  onChange={(event) => setSelectedItemId(Number(event.target.value))}
                  disabled={!actionable.length}
                >
                  {actionable.length ? (
                    actionable.map((item) => (
                      <option key={item.id} value={item.id}>{item.display_name}</option>
                    ))
                  ) : (
                    <option value="">No items yet</option>
                  )}
                </select>
                <ChevronDown size={15} />
              </div>

              <span className="bench-label">Event</span>
              <div className="bench-actions">
                {([["open", "Opened"], ["consume", "Eaten"], ["move", "Moved"]] as const)
                  .map(([key, label]) => (
                    <button
                      key={key}
                      className={stateAction === key ? "bench-action selected" : "bench-action"}
                      onClick={() => setStateAction(key)}
                    >
                      {label}
                    </button>
                  ))}
              </div>

              {stateAction === "move" ? (
                <>
                  <label className="bench-label" htmlFor="bench-location">New location</label>
                  <div className="bench-select">
                    <select
                      id="bench-location" value={moveLocation}
                      onChange={(event) =>
                        setMoveLocation(event.target.value as StorageLocation)}
                    >
                      <option value="pantry">Pantry</option>
                      <option value="refrigerator">Refrigerator</option>
                      <option value="freezer">Freezer</option>
                    </select>
                    <ChevronDown size={15} />
                  </div>
                </>
              ) : null}

              <button
                className="bench-fire" disabled={isWorking || !target}
                onClick={() => {
                  if (target) onStateEvent(target.id, stateAction, moveLocation);
                }}
              >
                {isWorking ? <LoaderCircle className="spin" size={15} /> : <Check size={15} />}
                {isWorking ? "Calling the tool" : "Fire the state event"}
                {!isWorking && <ArrowRight size={15} />}
              </button>
            </div>
          ) : mode === "context" ? (
            <div className="bench-form">
              <p className="bench-hint">
                Sends <code>update_pantry_context</code>. This is the one that
                shows voice beating a rules engine: what the person noticed out
                loud overrides the catalog shelf life, and the new date comes
                straight back from PostgreSQL.
              </p>
              <label className="bench-label" htmlFor="bench-context-item">Item</label>
              <div className="bench-select">
                <select
                  id="bench-context-item" value={targetId ?? ""}
                  onChange={(event) => setSelectedItemId(Number(event.target.value))}
                  disabled={!actionable.length}
                >
                  {actionable.length ? (
                    actionable.map((item) => (
                      <option key={item.id} value={item.id}>{item.display_name}</option>
                    ))
                  ) : (
                    <option value="">No items yet</option>
                  )}
                </select>
                <ChevronDown size={15} />
              </div>

              <label className="bench-label" htmlFor="bench-modifier">What was said</label>
              <div className="bench-select">
                <select
                  id="bench-modifier" value={modifier}
                  onChange={(event) =>
                    setModifier(event.target.value as RipenessModifier)}
                >
                  {(Object.keys(RIPENESS_UTTERANCES) as RipenessModifier[]).map((key) => (
                    <option key={key} value={key}>
                      {RIPENESS_UTTERANCES[key](target?.display_name ?? "item")}
                    </option>
                  ))}
                </select>
                <ChevronDown size={15} />
              </div>

              <button
                className="bench-fire" disabled={isWorking || !target}
                onClick={() => {
                  if (target) onContextEvent(target.display_name, modifier);
                }}
              >
                {isWorking
                  ? <LoaderCircle className="spin" size={15} />
                  : <MessageSquareQuote size={15} />}
                {isWorking ? "Calling the tool" : "Fire the spoken context"}
                {!isWorking && <ArrowRight size={15} />}
              </button>
            </div>
          ) : (
            <div className="bench-form">
              <p className="bench-hint">
                Sends <code>generate_and_adapt_recipe</code> and hands the screen
                over to the step card. This tool reasons with Amazon Bedrock, so
                without AWS credentials it fails -- and the screen shows that
                failure rather than a stand-in recipe.
              </p>
              <label className="bench-label" htmlFor="bench-servings">Servings</label>
              <div className="bench-select">
                <select
                  id="bench-servings" value={servings}
                  onChange={(event) => setServings(Number(event.target.value))}
                >
                  {[1, 2, 3, 4, 6].map((count) => (
                    <option key={count} value={count}>{count}</option>
                  ))}
                </select>
                <ChevronDown size={15} />
              </div>
              <button
                className="bench-fire" disabled={isWorking}
                onClick={() => onRecipe(servings)}
              >
                {isWorking ? <LoaderCircle className="spin" size={15} /> : <CookingPot size={15} />}
                {isWorking ? "Calling the tool" : "Ask what to cook"}
                {!isWorking && <ArrowRight size={15} />}
              </button>

              <div className="bench-ranout">
                <label className="bench-label" htmlFor="bench-ranout-item">
                  Ran out mid-cook
                </label>
                <p className="bench-hint">
                  Sends the same tool again with <code>prior_recipe</code> and
                  <code>exclude_items</code>. That is the adapt path rather than
                  the generate path: same dish, rebuilt without the thing you
                  just reached for and did not have.
                </p>
                <div className="bench-select">
                  <select
                    id="bench-ranout-item" value={ranOutTarget}
                    onChange={(event) => setRanOutItem(event.target.value)}
                    disabled={!pantryIngredients.length}
                  >
                    {pantryIngredients.length ? (
                      pantryIngredients.map((one) => (
                        <option key={one.name} value={one.name}>{one.name}</option>
                      ))
                    ) : (
                      <option value="">Ask what to cook first</option>
                    )}
                  </select>
                  <ChevronDown size={15} />
                </div>
                <button
                  className="bench-fire"
                  disabled={isWorking || !pantryIngredients.length}
                  onClick={() => { if (ranOutTarget) onRanOut(ranOutTarget); }}
                >
                  {isWorking
                    ? <LoaderCircle className="spin" size={15} />
                    : <CookingPot size={15} />}
                  {isWorking ? "Calling the tool" : "Fire: ran out"}
                  {!isWorking && <ArrowRight size={15} />}
                </button>
              </div>
            </div>
          )}

          {benchNote ? <p className="bench-note" role="status">{benchNote}</p> : null}
        </div>

        <div className="bench-log">
          <span className="bench-label">Call log</span>
          <div className="bench-log-list">
            {events.length ? events.slice(0, 5).map((event) => (
              <div className="bench-log-row" key={event.id}>
                <span className={`bench-log-mark mark-${event.kind}`}>
                  <EventMark kind={event.kind} />
                </span>
                <span className="bench-log-copy">
                  <strong>{event.title}</strong>
                  <small>{event.detail}</small>
                </span>
                <time>{event.time}</time>
              </div>
            )) : <p className="bench-hint">No events fired yet.</p>}
          </div>
        </div>
      </div>
    </section>
  );
}

"use client";

import {
  ArrowRight, Check, ChevronDown, CircleCheck, LoaderCircle, ScanLine,
  Settings2, Snowflake, Sparkles, Terminal, Upload, X,
} from "lucide-react";
import Image from "next/image";
import { useRef, useState, type ChangeEvent } from "react";
import {
  type DemoEvent, type InventoryItem, type StorageLocation,
} from "@/lib/kitchen-data";

export type StateAction = "open" | "consume" | "move";
type BenchMode = "receipt" | "state";

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
  items, events, isWorking, onReceipt, onStateEvent,
}: DevBenchProps) {
  const [mode, setMode] = useState<BenchMode>("receipt");
  const [stateAction, setStateAction] = useState<StateAction>("open");
  const [moveLocation, setMoveLocation] = useState<StorageLocation>("freezer");
  const [selectedItemId, setSelectedItemId] = useState<number | null>(null);
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
          ) : (
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

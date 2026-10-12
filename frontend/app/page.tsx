"use client";

import {
  Activity, ArrowRight, Bell, CalendarDays, Check, ChevronDown, CircleAlert,
  CircleCheck, Clock3, CloudOff, CookingPot, ImagePlus, Leaf, LoaderCircle,
  MapPin, Package, Plus, RotateCw, ScanLine, Search, Settings2, Snowflake,
  Sparkles, Upload, X,
} from "lucide-react";
import Image from "next/image";
import { StatusPill } from "@/components/status-pill";
import {
  useDeferredValue, useEffect, useRef, useState,
  type ChangeEvent, type CSSProperties, type DragEvent,
} from "react";
import {
  createDemoInventory, createDemoReceiptItems, DEMO_USER_ID, formatDate,
  initialDemoEvents, locationLabel,
  type DemoEvent, type InventoryItem,
  type InventoryStatusResponse, type StorageLocation,
} from "@/lib/kitchen-data";

type ConnectionState = "checking" | "demo" | "live";
type EventMode = "receipt" | "state";
type StateAction = "open" | "consume" | "move";
type InventoryFilter = "all" | "expiring_soon" | "expired" | "consumed";
type ToolName = "get_inventory_status" | "modify_item_state" | "ingest_receipt_items";

async function invokeTool<T>(tool: ToolName, args: Record<string, unknown>): Promise<T> {
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

function dayMessage(days: number | null): string {
  if (days === null) return "No date";
  if (days < 0) return `Expired ${Math.abs(days)} d ago`;
  if (days === 0) return "Expires today";
  if (days === 1) return "1 day left";
  return `${days} days left`;
}

function EventMark({ kind }: { kind: DemoEvent["kind"] }) {
  if (kind === "receipt") return <ScanLine size={15} />;
  if (kind === "opened") return <Sparkles size={15} />;
  if (kind === "consumed") return <CircleCheck size={15} />;
  return <Snowflake size={15} />;
}

export default function Home() {
  const [items, setItems] = useState<InventoryItem[]>(createDemoInventory);
  const [events, setEvents] = useState<DemoEvent[]>(initialDemoEvents);
  const [connection, setConnection] = useState<ConnectionState>("checking");
  const [mode, setMode] = useState<EventMode>("receipt");
  const [stateAction, setStateAction] = useState<StateAction>("open");
  const [selectedItemId, setSelectedItemId] = useState(101);
  const [moveLocation, setMoveLocation] = useState<StorageLocation>("freezer");
  const [filter, setFilter] = useState<InventoryFilter>("all");
  const [locationFilter, setLocationFilter] = useState<"all" | StorageLocation>("all");
  const [search, setSearch] = useState("");
  const deferredSearch = useDeferredValue(search);
  const [receiptFile, setReceiptFile] = useState<File | null>(null);
  const [receiptPreview, setReceiptPreview] = useState("");
  const [isWorking, setIsWorking] = useState(false);
  const [toast, setToast] = useState("");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let active = true;
    invokeTool<InventoryStatusResponse>("get_inventory_status", {
      user_id: DEMO_USER_ID,
      include_consumed: true,
    }).then((data) => {
      if (!active || !Array.isArray(data.items)) return;
      setItems(data.items);
      setSelectedItemId(data.items.find((item) => item.status !== "consumed")?.id ?? 0);
      setConnection("live");
    }).catch(() => {
      if (active) setConnection("demo");
    });
    return () => { active = false; };
  }, []);

  useEffect(() => {
    if (!toast) return;
    const timer = window.setTimeout(() => setToast(""), 3200);
    return () => window.clearTimeout(timer);
  }, [toast]);

  const activeItems = items.filter((item) => item.status !== "consumed");
  const soonCount = activeItems.filter((item) => item.status === "expiring_soon").length;
  const expiredCount = activeItems.filter((item) => item.status === "expired").length;
  const freshCount = activeItems.filter((item) => item.status === "fresh").length;
  const deferredNeedle = deferredSearch.trim().toLocaleLowerCase("en");
  const visibleItems = items.filter((item) => {
    const matchesFilter = filter === "all" || item.status === filter;
    const matchesLocation = locationFilter === "all" || item.storage_location === locationFilter;
    const matchesSearch = !deferredNeedle ||
      item.display_name.toLocaleLowerCase("en").includes(deferredNeedle) ||
      (item.ingredient_name ?? "").toLocaleLowerCase("en").includes(deferredNeedle);
    return matchesFilter && matchesLocation && matchesSearch;
  });
  const selectedItem = items.find((item) => item.id === selectedItemId);

  function announce(title: string, detail: string, kind: DemoEvent["kind"]) {
    setEvents((current) => [{
      id: Date.now(), title, detail,
      time: new Intl.DateTimeFormat("en", { hour: "2-digit", minute: "2-digit" }).format(new Date()),
      kind,
    }, ...current].slice(0, 5));
  }

  async function refreshInventory() {
    const data = await invokeTool<InventoryStatusResponse>("get_inventory_status", {
      user_id: DEMO_USER_ID,
      include_consumed: true,
    });
    if (!Array.isArray(data.items)) throw new Error("The inventory received is not valid.");
    setItems(data.items);
    setSelectedItemId(data.items.find((item) => item.status !== "consumed")?.id ?? 0);
    setConnection("live");
  }

  async function retryConnection() {
    setConnection("checking");
    try {
      await refreshInventory();
      setToast("Inventory connection restored.");
    } catch {
      setConnection("demo");
      setToast("Backend unavailable. Still in demo mode.");
    }
  }

  function acceptReceipt(file: File | undefined) {
    if (!file) return;
    if (!["image/jpeg", "image/png", "image/gif", "image/webp"].includes(file.type)) {
      setToast("Use a JPEG, PNG, GIF or WebP image.");
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      setToast("The photo must be 5 MB or less.");
      return;
    }
    if (receiptPreview) URL.revokeObjectURL(receiptPreview);
    setReceiptFile(file);
    setReceiptPreview(URL.createObjectURL(file));
  }

  function onFileChange(event: ChangeEvent<HTMLInputElement>) {
    acceptReceipt(event.target.files?.[0]);
  }

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    acceptReceipt(event.dataTransfer.files[0]);
  }

  async function processReceipt() {
    if (!receiptFile) {
      fileInputRef.current?.click();
      return;
    }
    setIsWorking(true);
    try {
      const imageBase64 = await fileToBase64(receiptFile);
      if (connection === "live") {
        const result = await invokeTool<{ success: boolean; count: number }>("ingest_receipt_items", {
          user_id: DEMO_USER_ID,
          image_base64: imageBase64,
          media_type: receiptFile.type,
        });
        if (!result.success) throw new Error("The receipt could not be processed.");
        await refreshInventory();
        announce("Receipt processed", `${result.count} products added from the photo`, "receipt");
        setToast(`${result.count} products added to the inventory.`);
        return;
      }
      const newItems = createDemoReceiptItems(Date.now());
      setItems((current) => [...newItems, ...current]);
      announce("Receipt simulated", "2 products added in demo mode", "receipt");
      setToast("Receipt simulated. 2 sample products were added.");
    } catch (error) {
      setToast(error instanceof Error ? error.message : "Could not read the photo.");
    } finally {
      setIsWorking(false);
    }
  }

  async function submitStateEvent() {
    if (!selectedItem) {
      setToast("There are no items to modify.");
      return;
    }

    setIsWorking(true);
    const itemId = selectedItem.id;
    const actionLabel = stateAction === "open"
      ? "Item marked as opened"
      : stateAction === "consume"
        ? "Item marked as consumed"
        : `Item moved to the ${locationLabel(moveLocation).toLowerCase()}`;
    const detail = `${selectedItem.display_name} · now`;

    try {
      if (connection === "live") {
        const argumentsForTool: Record<string, unknown> = {
          user_id: DEMO_USER_ID,
          item_id: itemId,
        };
        if (stateAction === "open") {
          argumentsForTool.is_opened = true;
          argumentsForTool.opened_date = todayIso();
        } else if (stateAction === "consume") {
          argumentsForTool.is_consumed = true;
        } else {
          argumentsForTool.storage_location = moveLocation;
        }
        const result = await invokeTool<{ success: boolean; error?: string }>(
          "modify_item_state",
          argumentsForTool,
        );
        if (!result.success) throw new Error(result.error ?? "Could not update.");
        await refreshInventory();
        announce(actionLabel, detail, stateAction === "open" ? "opened" : stateAction === "consume" ? "consumed" : "moved");
        setToast("Event applied to the inventory.");
        return;
      }

      setItems((current) => current.map((item) => {
        if (item.id !== itemId) return item;
        if (stateAction === "open") return { ...item, is_opened: true };
        if (stateAction === "consume") return { ...item, status: "consumed", quantity: "0.00" };
        return { ...item, storage_location: moveLocation };
      }));
      if (stateAction === "consume") {
        setSelectedItemId(items.find((item) => item.id !== itemId && item.status !== "consumed")?.id ?? 0);
      }
      announce(actionLabel, detail, stateAction === "open" ? "opened" : stateAction === "consume" ? "consumed" : "moved");
      setToast("Event applied in the local simulator.");
    } catch (error) {
      setToast(error instanceof Error ? error.message : "Could not apply the event.");
    } finally {
      setIsWorking(false);
    }
  }

  function consumeFromRow(item: InventoryItem) {
    if (connection === "live") {
      setSelectedItemId(item.id);
      setStateAction("consume");
      setMode("state");
      setToast("Choose “Apply event” in the simulator to confirm it was consumed.");
      return;
    }
    setItems((current) => current.map((entry) => entry.id === item.id
      ? { ...entry, status: "consumed", quantity: "0.00" }
      : entry));
    setSelectedItemId(items.find((entry) => entry.id !== item.id && entry.status !== "consumed")?.id ?? 0);
    announce("Item marked as consumed", `${item.display_name} · now`, "consumed");
    setToast(`${item.display_name} marked as consumed.`);
  }

  const filterOptions: Array<{ key: InventoryFilter; label: string }> = [
    { key: "all", label: "All" },
    { key: "expiring_soon", label: "Expiring soon" },
    { key: "expired", label: "Expired" },
    { key: "consumed", label: "Consumed" },
  ];

  return (
    <main className="kitchen-app">
      <header className="topbar">
        <a className="brand-lockup" href="#home" aria-label="Eat Me First, home">
          <span className="brand-mark"><CookingPot size={19} strokeWidth={2.2} /></span>
          <span className="brand-name">eat me<span>first</span></span>
        </a>
        <nav className="top-nav" aria-label="Main navigation">
          <a className="top-nav-link active" href="#inventory">Kitchen</a>
          <a className="top-nav-link" href="#events">Events</a>
          <a className="top-nav-link" href="#inventory">Inventory</a>
        </nav>
        <div className="topbar-tools">
          <button className="icon-button topbar-icon" title="Notifications" aria-label="Notifications" onClick={() => setToast("No new notifications.")}><Bell size={18} /><span className="notification-dot" /></button>
          <span className={`connection-badge connection-${connection}`}>
            <span className="connection-light" />
            {connection === "live" ? "MCP live" : connection === "checking" ? "Connecting" : "Demo mode"}
          </span>
          <button className="profile-chip" title="Demo user" onClick={() => setToast(`Demo session · user ${DEMO_USER_ID}`)}>
            <span className="profile-avatar">CV</span>
            <span className="profile-copy"><strong>Green House</strong><small>User {DEMO_USER_ID}</small></span>
            <ChevronDown size={14} />
          </button>
        </div>
      </header>

      <div className="workspace" id="home">
        <aside className="event-panel" id="events">
          <div className="panel-heading">
            <div><span className="eyebrow light-eyebrow"><Activity size={13} /> Activity center</span><h1>Event<br />simulator</h1></div>
            <span className="panel-index">01 / 02</span>
          </div>
          <div className="mode-switch" role="tablist" aria-label="Event type">
            <button role="tab" aria-selected={mode === "receipt"} className={mode === "receipt" ? "mode-tab selected" : "mode-tab"} onClick={() => setMode("receipt")}><ScanLine size={16} /> Receipt</button>
            <button role="tab" aria-selected={mode === "state"} className={mode === "state" ? "mode-tab selected" : "mode-tab"} onClick={() => setMode("state")}><Settings2 size={16} /> State</button>
          </div>

          {mode === "receipt" ? (
            <section className="event-form" aria-label="Simulate reading a receipt">
              <div className="form-title-row"><div><span className="eyebrow light-eyebrow">01 · Input</span><h2>Scan a shop</h2></div><span className="ai-stamp"><Sparkles size={13} /> AI</span></div>
              <p className="panel-copy">Upload a photo of a receipt and turn its lines into inventory.</p>
              <input ref={fileInputRef} className="visually-hidden" type="file" aria-hidden="true" tabIndex={-1} accept="image/jpeg,image/png,image/gif,image/webp" onChange={onFileChange} />
              <div className={`receipt-dropzone ${receiptPreview ? "has-preview" : ""}`} onDragOver={(event) => event.preventDefault()} onDrop={onDrop}>
                {receiptPreview ? <>
                  <Image className="receipt-preview" src={receiptPreview} alt="Receipt preview" width={640} height={360} unoptimized />
                  <button className="remove-preview icon-button" title="Remove photo" aria-label="Remove photo" onClick={() => { URL.revokeObjectURL(receiptPreview); setReceiptPreview(""); setReceiptFile(null); }}><X size={15} /></button>
                  <span className="receipt-filename">{receiptFile?.name}</span>
                </> : <>
                  <span className="upload-icon"><ImagePlus size={21} /></span>
                  <strong>Drag the receipt here</strong>
                  <span>JPG, PNG or WEBP · 5 MB maximum</span>
                  <button className="choose-file-button" onClick={() => fileInputRef.current?.click()}><Upload size={14} /> Choose image</button>
                </>}
              </div>
              <button className="primary-event-button" onClick={processReceipt} disabled={isWorking}>
                {isWorking ? <LoaderCircle className="spin" size={17} /> : <Sparkles size={16} />}
                {isWorking ? "Processing receipt" : receiptFile ? "Analyze and add" : "Choose a receipt to analyze"}
                {!isWorking && <ArrowRight size={16} />}
              </button>
              <p className="privacy-note"><Leaf size={13} /> The photo is used only to extract products.</p>
            </section>
          ) : (
            <section className="event-form" aria-label="Simulate a state change">
              <div className="form-title-row"><div><span className="eyebrow light-eyebrow">02 · Action</span><h2>Update an item</h2></div><span className="ai-stamp muted-stamp"><Settings2 size={13} /> MANUAL</span></div>
              <p className="panel-copy">Simulate an everyday action and watch your kitchen change.</p>
              <label className="field-label" htmlFor="item-select">Item</label>
              <div className="select-wrap">
                <select id="item-select" value={selectedItemId} onChange={(event) => setSelectedItemId(Number(event.target.value))}>
                  {items.filter((item) => item.status !== "consumed").map((item) => <option key={item.id} value={item.id}>{item.display_name}</option>)}
                </select><ChevronDown size={15} />
              </div>
              <span className="field-label action-label">Event</span>
              <div className="action-options">
                <button className={stateAction === "open" ? "action-option selected" : "action-option"} onClick={() => setStateAction("open")}><Sparkles size={16} /><span>Open</span></button>
                <button className={stateAction === "consume" ? "action-option selected" : "action-option"} onClick={() => setStateAction("consume")}><Check size={16} /><span>Consume</span></button>
                <button className={stateAction === "move" ? "action-option selected" : "action-option"} onClick={() => setStateAction("move")}><Snowflake size={16} /><span>Move</span></button>
              </div>
              {stateAction === "move" ? <>
                <label className="field-label" htmlFor="location-select">New location</label>
                <div className="select-wrap"><select id="location-select" value={moveLocation} onChange={(event) => setMoveLocation(event.target.value as StorageLocation)}><option value="pantry">Pantry</option><option value="refrigerator">Refrigerator</option><option value="freezer">Freezer</option></select><ChevronDown size={15} /></div>
              </> : <div className="event-context">{stateAction === "open" ? <CalendarDays size={15} /> : <CircleCheck size={15} />}<span>{stateAction === "open" ? `Opened date · ${formatDate(todayIso())}` : "The quantity will be marked as consumed"}</span></div>}
              <button className="primary-event-button state-submit" onClick={submitStateEvent} disabled={isWorking || !selectedItem}>
                {isWorking ? <LoaderCircle className="spin" size={17} /> : <Check size={16} />}{isWorking ? "Applying event" : "Apply event"}{!isWorking && <ArrowRight size={16} />}
              </button>
            </section>
          )}

          <section className="event-history">
            <div className="history-heading"><span className="eyebrow light-eyebrow">Recent log</span><button className="history-count" title={`${events.length} recent events`}>{String(events.length).padStart(2, "0")}</button></div>
            <div className="event-list">{events.slice(0, 3).map((event) => <div className="event-entry" key={event.id}>
              <span className={`event-mark mark-${event.kind}`}><EventMark kind={event.kind} /></span>
              <span className="event-entry-copy"><strong>{event.title}</strong><small>{event.detail}</small></span><time>{event.time}</time>
            </div>)}</div>
          </section>
          <div className="panel-footnote"><span className="footnote-line" /> ZERO WASTE · EVERY DAY</div>
        </aside>

        <section className="inventory-panel" id="inventory">
          <div className="inventory-topline">
            <div><span className="eyebrow"><span className="eyebrow-square" /> Kitchen panel · My inventory</span><h2>Inventory <em>traffic light</em></h2><p className="inventory-subtitle">What matters, fresh and on time.</p></div>
            <div className="topline-actions">
              <button className="sync-button" onClick={retryConnection} disabled={connection === "checking"} title="Sync with the backend">{connection === "checking" ? <LoaderCircle className="spin" size={15} /> : <RotateCw size={15} />}<span>{connection === "live" ? "Synced" : "Retry"}</span></button>
              <button className="add-button" onClick={() => { setMode("receipt"); document.getElementById("events")?.scrollIntoView({ behavior: "smooth" }); }}><Plus size={17} /><span>Add a shop</span></button>
            </div>
          </div>

          <div className="summary-strip" aria-label="Inventory summary">
            <div className="summary-cell"><span className="summary-icon summary-total"><Package size={17} /></span><span className="summary-copy"><strong>{activeItems.length}</strong><small>active items</small></span></div>
            <div className="summary-cell"><span className="summary-icon summary-soon"><Clock3 size={17} /></span><span className="summary-copy"><strong>{soonCount.toString().padStart(2, "0")}</strong><small>expiring soon</small></span></div>
            <div className="summary-cell"><span className="summary-icon summary-expired"><CircleAlert size={17} /></span><span className="summary-copy"><strong>{expiredCount.toString().padStart(2, "0")}</strong><small>need attention</small></span></div>
            <div className="summary-note"><span className="fresh-ring"><Leaf size={15} /></span><span><strong>{freshCount} fresh</strong><small>Your kitchen is doing well</small></span></div>
          </div>

          <div className="inventory-toolbar">
            <div className="filter-tabs" role="tablist" aria-label="Filter by status">
              {filterOptions.map((option) => <button key={option.key} role="tab" aria-selected={filter === option.key} className={filter === option.key ? "filter-tab active" : "filter-tab"} onClick={() => setFilter(option.key)}>
                {option.label}{option.key === "expiring_soon" && soonCount > 0 && <span className="tab-count">{soonCount}</span>}
              </button>)}
            </div>
            <div className="inventory-controls">
              <label className="search-box"><Search size={16} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search the pantry" aria-label="Search the pantry" />{search && <button title="Clear search" aria-label="Clear search" onClick={() => setSearch("")}><X size={14} /></button>}</label>
              <label className="location-filter" title="Filter by location"><MapPin size={14} /><select value={locationFilter} onChange={(event) => setLocationFilter(event.target.value as "all" | StorageLocation)} aria-label="Filter by location"><option value="all">Location</option><option value="pantry">Pantry</option><option value="refrigerator">Refrigerator</option><option value="freezer">Freezer</option></select><ChevronDown size={13} /></label>
            </div>
          </div>

          <div className="inventory-list-head"><span>Item</span><span>Location</span><span>Quantity</span><span>Expiry</span><span>Status</span><span className="sr-only">Actions</span></div>
          <div className="inventory-list" aria-live="polite">
            {visibleItems.length ? visibleItems.map((item, index) => <article className={`inventory-row ${selectedId === item.id ? "row-selected" : ""}`} key={item.id} style={{ "--row-index": index } as CSSProperties} onClick={() => setSelectedId(selectedId === item.id ? null : item.id)}>
              <div className="product-cell"><span className={`product-mark product-${item.status}`}><span>{item.display_name.slice(0, 1).toLocaleUpperCase("en")}</span></span><span className="product-copy"><strong>{item.display_name}</strong><small>{item.ingredient_name ?? "Free item"}</small></span></div>
              <span className="location-cell"><MapPin size={14} />{locationLabel(item.storage_location)}</span>
              <span className="quantity-cell"><strong>{item.quantity}</strong><small>{item.unit}</small></span>
              <span className="expiry-cell"><strong>{formatDate(item.expiration_date)}</strong><small>{dayMessage(item.days_remaining)}</small></span>
              <span className="status-cell"><StatusPill status={item.status} /></span>
              <button className="row-action" title={`Mark ${item.display_name} as consumed`} aria-label={`Mark ${item.display_name} as consumed`} disabled={item.status === "consumed"} onClick={(event) => { event.stopPropagation(); consumeFromRow(item); }}><Check size={15} /></button>
            </article>) : <div className="empty-state"><span className="empty-icon"><Package size={21} /></span><strong>No items in this view</strong><span>Adjust the filters or record a shop.</span><button onClick={() => { setFilter("all"); setLocationFilter("all"); setSearch(""); }}>Clear filters</button></div>}
          </div>

          <footer className="inventory-footer"><span>Showing <strong>{visibleItems.length}</strong> of <strong>{items.length}</strong> records</span><span className="footer-updated"><span className={`footer-dot ${connection}`} />{connection === "live" ? "Updated from PostgreSQL" : "Demo data"}</span></footer>
          <div className="inventory-bottom-note"><span><CalendarDays size={14} /> Expiry dates are calculated in the database.</span><span>MADE TO WASTE LESS <ArrowRight size={13} /></span></div>
        </section>
      </div>

      {connection === "demo" && <div className="demo-ribbon"><CloudOff size={13} /> Backend disconnected · local demo changes</div>}
      {toast && <div className="toast-message" role="status"><CircleCheck size={17} />{toast}<button onClick={() => setToast("")} title="Close notice" aria-label="Close notice"><X size={14} /></button></div>}
    </main>
  );
}

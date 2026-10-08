"use client";

import {
  Activity, ArrowRight, Bell, CalendarDays, Check, ChevronDown, CircleAlert,
  CircleCheck, Clock3, CloudOff, CookingPot, ImagePlus, Leaf, LoaderCircle,
  MapPin, Package, Plus, RotateCw, ScanLine, Search, Settings2, Snowflake,
  Sparkles, Upload, X,
} from "lucide-react";
import Image from "next/image";
import {
  useDeferredValue, useEffect, useRef, useState,
  type ChangeEvent, type CSSProperties, type DragEvent,
} from "react";
import {
  createDemoInventory, createDemoReceiptItems, DEMO_USER_ID, formatDate,
  initialDemoEvents, locationLabel, statusLabel,
  type DemoEvent, type InventoryItem, type InventoryStatus,
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
    throw new Error(payload.error ?? "No se pudo conectar con MCP.");
  }
  return payload.data;
}

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const dataUrl = String(reader.result ?? "");
      const comma = dataUrl.indexOf(",");
      if (comma < 0) reject(new Error("No se pudo leer la imagen."));
      else resolve(dataUrl.slice(comma + 1));
    };
    reader.onerror = () => reject(new Error("No se pudo leer la imagen."));
    reader.readAsDataURL(file);
  });
}

function todayIso(): string {
  const date = new Date();
  const offset = date.getTimezoneOffset();
  return new Date(date.getTime() - offset * 60_000).toISOString().slice(0, 10);
}

function dayMessage(days: number | null): string {
  if (days === null) return "Sin fecha";
  if (days < 0) return `Venció hace ${Math.abs(days)} d`;
  if (days === 0) return "Vence hoy";
  if (days === 1) return "Queda 1 día";
  return `Quedan ${days} días`;
}

function EventMark({ kind }: { kind: DemoEvent["kind"] }) {
  if (kind === "receipt") return <ScanLine size={15} />;
  if (kind === "opened") return <Sparkles size={15} />;
  if (kind === "consumed") return <CircleCheck size={15} />;
  return <Snowflake size={15} />;
}

function StatusPill({ status }: { status: InventoryStatus }) {
  return <span className={`status-pill status-${status}`}><span className="status-dot" />{statusLabel(status)}</span>;
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
  const deferredNeedle = deferredSearch.trim().toLocaleLowerCase("es");
  const visibleItems = items.filter((item) => {
    const matchesFilter = filter === "all" || item.status === filter;
    const matchesLocation = locationFilter === "all" || item.storage_location === locationFilter;
    const matchesSearch = !deferredNeedle ||
      item.display_name.toLocaleLowerCase("es").includes(deferredNeedle) ||
      (item.ingredient_name ?? "").toLocaleLowerCase("es").includes(deferredNeedle);
    return matchesFilter && matchesLocation && matchesSearch;
  });
  const selectedItem = items.find((item) => item.id === selectedItemId);

  function announce(title: string, detail: string, kind: DemoEvent["kind"]) {
    setEvents((current) => [{
      id: Date.now(), title, detail,
      time: new Intl.DateTimeFormat("es", { hour: "2-digit", minute: "2-digit" }).format(new Date()),
      kind,
    }, ...current].slice(0, 5));
  }

  async function refreshInventory() {
    const data = await invokeTool<InventoryStatusResponse>("get_inventory_status", {
      user_id: DEMO_USER_ID,
      include_consumed: true,
    });
    if (!Array.isArray(data.items)) throw new Error("El inventario recibido no es válido.");
    setItems(data.items);
    setSelectedItemId(data.items.find((item) => item.status !== "consumed")?.id ?? 0);
    setConnection("live");
  }

  async function retryConnection() {
    setConnection("checking");
    try {
      await refreshInventory();
      setToast("Conexión con el inventario restablecida.");
    } catch {
      setConnection("demo");
      setToast("Backend no disponible. Sigues en modo demo.");
    }
  }

  function acceptReceipt(file: File | undefined) {
    if (!file) return;
    if (!["image/jpeg", "image/png", "image/gif", "image/webp"].includes(file.type)) {
      setToast("Usa una imagen JPEG, PNG, GIF o WebP.");
      return;
    }
    if (file.size > 5 * 1024 * 1024) {
      setToast("La foto debe pesar 5 MB o menos.");
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
        if (!result.success) throw new Error("El recibo no se pudo procesar.");
        await refreshInventory();
        announce("Recibo procesado", `${result.count} productos agregados desde la foto`, "receipt");
        setToast(`${result.count} productos añadidos al inventario.`);
        return;
      }
      const newItems = createDemoReceiptItems(Date.now());
      setItems((current) => [...newItems, ...current]);
      announce("Recibo simulado", "2 productos añadidos en modo demo", "receipt");
      setToast("Recibo simulado. Se añadieron 2 productos de ejemplo.");
    } catch (error) {
      setToast(error instanceof Error ? error.message : "No se pudo leer la foto.");
    } finally {
      setIsWorking(false);
    }
  }

  async function submitStateEvent() {
    if (!selectedItem) {
      setToast("No hay artículos para modificar.");
      return;
    }

    setIsWorking(true);
    const itemId = selectedItem.id;
    const actionLabel = stateAction === "open"
      ? "Artículo marcado como abierto"
      : stateAction === "consume"
        ? "Artículo marcado como consumido"
        : `Artículo movido a ${locationLabel(moveLocation).toLowerCase()}`;
    const detail = `${selectedItem.display_name} · ahora`;

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
        if (!result.success) throw new Error(result.error ?? "No se pudo actualizar.");
        await refreshInventory();
        announce(actionLabel, detail, stateAction === "open" ? "opened" : stateAction === "consume" ? "consumed" : "moved");
        setToast("Evento aplicado al inventario.");
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
      setToast("Evento aplicado en el simulador local.");
    } catch (error) {
      setToast(error instanceof Error ? error.message : "No se pudo aplicar el evento.");
    } finally {
      setIsWorking(false);
    }
  }

  function consumeFromRow(item: InventoryItem) {
    if (connection === "live") {
      setSelectedItemId(item.id);
      setStateAction("consume");
      setMode("state");
      setToast("Elige «Aplicar evento» en el simulador para confirmar el consumo.");
      return;
    }
    setItems((current) => current.map((entry) => entry.id === item.id
      ? { ...entry, status: "consumed", quantity: "0.00" }
      : entry));
    setSelectedItemId(items.find((entry) => entry.id !== item.id && entry.status !== "consumed")?.id ?? 0);
    announce("Artículo marcado como consumido", `${item.display_name} · ahora`, "consumed");
    setToast(`${item.display_name} marcado como consumido.`);
  }

  const filterOptions: Array<{ key: InventoryFilter; label: string }> = [
    { key: "all", label: "Todo" },
    { key: "expiring_soon", label: "Por vencer" },
    { key: "expired", label: "Vencido" },
    { key: "consumed", label: "Consumido" },
  ];

  return (
    <main className="kitchen-app">
      <header className="topbar">
        <a className="brand-lockup" href="#inicio" aria-label="Despensa Viva, inicio">
          <span className="brand-mark"><CookingPot size={19} strokeWidth={2.2} /></span>
          <span className="brand-name">despensa<span>viva</span></span>
        </a>
        <nav className="top-nav" aria-label="Navegación principal">
          <a className="top-nav-link active" href="#inventario">Cocina</a>
          <a className="top-nav-link" href="#eventos">Eventos</a>
          <a className="top-nav-link" href="#inventario">Inventario</a>
        </nav>
        <div className="topbar-tools">
          <button className="icon-button topbar-icon" title="Notificaciones" aria-label="Notificaciones" onClick={() => setToast("No hay notificaciones nuevas.")}><Bell size={18} /><span className="notification-dot" /></button>
          <span className={`connection-badge connection-${connection}`}>
            <span className="connection-light" />
            {connection === "live" ? "MCP en vivo" : connection === "checking" ? "Conectando" : "Modo demo"}
          </span>
          <button className="profile-chip" title="Usuario de demostración" onClick={() => setToast(`Sesión de demostración · usuario ${DEMO_USER_ID}`)}>
            <span className="profile-avatar">CV</span>
            <span className="profile-copy"><strong>Casa Verde</strong><small>Usuario {DEMO_USER_ID}</small></span>
            <ChevronDown size={14} />
          </button>
        </div>
      </header>

      <div className="workspace" id="inicio">
        <aside className="event-panel" id="eventos">
          <div className="panel-heading">
            <div><span className="eyebrow light-eyebrow"><Activity size={13} /> Centro de actividad</span><h1>Simulador<br />de eventos</h1></div>
            <span className="panel-index">01 / 02</span>
          </div>
          <div className="mode-switch" role="tablist" aria-label="Tipo de evento">
            <button role="tab" aria-selected={mode === "receipt"} className={mode === "receipt" ? "mode-tab selected" : "mode-tab"} onClick={() => setMode("receipt")}><ScanLine size={16} /> Recibo</button>
            <button role="tab" aria-selected={mode === "state"} className={mode === "state" ? "mode-tab selected" : "mode-tab"} onClick={() => setMode("state")}><Settings2 size={16} /> Estado</button>
          </div>

          {mode === "receipt" ? (
            <section className="event-form" aria-label="Simular lectura de recibo">
              <div className="form-title-row"><div><span className="eyebrow light-eyebrow">01 · Entrada</span><h2>Escanea una compra</h2></div><span className="ai-stamp"><Sparkles size={13} /> IA</span></div>
              <p className="panel-copy">Sube la foto de un recibo y convierte sus líneas en inventario.</p>
              <input ref={fileInputRef} className="visually-hidden" type="file" aria-hidden="true" tabIndex={-1} accept="image/jpeg,image/png,image/gif,image/webp" onChange={onFileChange} />
              <div className={`receipt-dropzone ${receiptPreview ? "has-preview" : ""}`} onDragOver={(event) => event.preventDefault()} onDrop={onDrop}>
                {receiptPreview ? <>
                  <Image className="receipt-preview" src={receiptPreview} alt="Vista previa del recibo" width={640} height={360} unoptimized />
                  <button className="remove-preview icon-button" title="Quitar foto" aria-label="Quitar foto" onClick={() => { URL.revokeObjectURL(receiptPreview); setReceiptPreview(""); setReceiptFile(null); }}><X size={15} /></button>
                  <span className="receipt-filename">{receiptFile?.name}</span>
                </> : <>
                  <span className="upload-icon"><ImagePlus size={21} /></span>
                  <strong>Arrastra el recibo aquí</strong>
                  <span>JPG, PNG o WEBP · máximo 5 MB</span>
                  <button className="choose-file-button" onClick={() => fileInputRef.current?.click()}><Upload size={14} /> Elegir imagen</button>
                </>}
              </div>
              <button className="primary-event-button" onClick={processReceipt} disabled={isWorking}>
                {isWorking ? <LoaderCircle className="spin" size={17} /> : <Sparkles size={16} />}
                {isWorking ? "Procesando recibo" : receiptFile ? "Analizar y agregar" : "Elegir recibo para analizar"}
                {!isWorking && <ArrowRight size={16} />}
              </button>
              <p className="privacy-note"><Leaf size={13} /> La foto se usa solo para extraer productos.</p>
            </section>
          ) : (
            <section className="event-form" aria-label="Simular cambio de estado">
              <div className="form-title-row"><div><span className="eyebrow light-eyebrow">02 · Acción</span><h2>Actualiza un artículo</h2></div><span className="ai-stamp muted-stamp"><Settings2 size={13} /> MANUAL</span></div>
              <p className="panel-copy">Simula una acción cotidiana y observa el cambio en tu cocina.</p>
              <label className="field-label" htmlFor="item-select">Artículo</label>
              <div className="select-wrap">
                <select id="item-select" value={selectedItemId} onChange={(event) => setSelectedItemId(Number(event.target.value))}>
                  {items.filter((item) => item.status !== "consumed").map((item) => <option key={item.id} value={item.id}>{item.display_name}</option>)}
                </select><ChevronDown size={15} />
              </div>
              <span className="field-label action-label">Evento</span>
              <div className="action-options">
                <button className={stateAction === "open" ? "action-option selected" : "action-option"} onClick={() => setStateAction("open")}><Sparkles size={16} /><span>Abrir</span></button>
                <button className={stateAction === "consume" ? "action-option selected" : "action-option"} onClick={() => setStateAction("consume")}><Check size={16} /><span>Consumir</span></button>
                <button className={stateAction === "move" ? "action-option selected" : "action-option"} onClick={() => setStateAction("move")}><Snowflake size={16} /><span>Mover</span></button>
              </div>
              {stateAction === "move" ? <>
                <label className="field-label" htmlFor="location-select">Nueva ubicación</label>
                <div className="select-wrap"><select id="location-select" value={moveLocation} onChange={(event) => setMoveLocation(event.target.value as StorageLocation)}><option value="pantry">Despensa</option><option value="refrigerator">Refrigerador</option><option value="freezer">Congelador</option></select><ChevronDown size={15} /></div>
              </> : <div className="event-context">{stateAction === "open" ? <CalendarDays size={15} /> : <CircleCheck size={15} />}<span>{stateAction === "open" ? `Fecha de apertura · ${formatDate(todayIso())}` : "La cantidad se marcará como consumida"}</span></div>}
              <button className="primary-event-button state-submit" onClick={submitStateEvent} disabled={isWorking || !selectedItem}>
                {isWorking ? <LoaderCircle className="spin" size={17} /> : <Check size={16} />}{isWorking ? "Aplicando evento" : "Aplicar evento"}{!isWorking && <ArrowRight size={16} />}
              </button>
            </section>
          )}

          <section className="event-history">
            <div className="history-heading"><span className="eyebrow light-eyebrow">Registro reciente</span><button className="history-count" title={`${events.length} eventos recientes`}>{String(events.length).padStart(2, "0")}</button></div>
            <div className="event-list">{events.slice(0, 3).map((event) => <div className="event-entry" key={event.id}>
              <span className={`event-mark mark-${event.kind}`}><EventMark kind={event.kind} /></span>
              <span className="event-entry-copy"><strong>{event.title}</strong><small>{event.detail}</small></span><time>{event.time}</time>
            </div>)}</div>
          </section>
          <div className="panel-footnote"><span className="footnote-line" /> ZERO WASTE · TODOS LOS DÍAS</div>
        </aside>

        <section className="inventory-panel" id="inventario">
          <div className="inventory-topline">
            <div><span className="eyebrow"><span className="eyebrow-square" /> Panel de cocina · Mi inventario</span><h2>Semáforo de <em>inventario</em></h2><p className="inventory-subtitle">Lo importante, fresco y a tiempo.</p></div>
            <div className="topline-actions">
              <button className="sync-button" onClick={retryConnection} disabled={connection === "checking"} title="Sincronizar con el backend">{connection === "checking" ? <LoaderCircle className="spin" size={15} /> : <RotateCw size={15} />}<span>{connection === "live" ? "Sincronizado" : "Reintentar"}</span></button>
              <button className="add-button" onClick={() => { setMode("receipt"); document.getElementById("eventos")?.scrollIntoView({ behavior: "smooth" }); }}><Plus size={17} /><span>Añadir compra</span></button>
            </div>
          </div>

          <div className="summary-strip" aria-label="Resumen del inventario">
            <div className="summary-cell"><span className="summary-icon summary-total"><Package size={17} /></span><span className="summary-copy"><strong>{activeItems.length}</strong><small>artículos activos</small></span></div>
            <div className="summary-cell"><span className="summary-icon summary-soon"><Clock3 size={17} /></span><span className="summary-copy"><strong>{soonCount.toString().padStart(2, "0")}</strong><small>por vencer pronto</small></span></div>
            <div className="summary-cell"><span className="summary-icon summary-expired"><CircleAlert size={17} /></span><span className="summary-copy"><strong>{expiredCount.toString().padStart(2, "0")}</strong><small>necesitan atención</small></span></div>
            <div className="summary-note"><span className="fresh-ring"><Leaf size={15} /></span><span><strong>{freshCount} en buen estado</strong><small>Tu cocina va bien</small></span></div>
          </div>

          <div className="inventory-toolbar">
            <div className="filter-tabs" role="tablist" aria-label="Filtrar por estado">
              {filterOptions.map((option) => <button key={option.key} role="tab" aria-selected={filter === option.key} className={filter === option.key ? "filter-tab active" : "filter-tab"} onClick={() => setFilter(option.key)}>
                {option.label}{option.key === "expiring_soon" && soonCount > 0 && <span className="tab-count">{soonCount}</span>}
              </button>)}
            </div>
            <div className="inventory-controls">
              <label className="search-box"><Search size={16} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Buscar en la despensa" aria-label="Buscar en la despensa" />{search && <button title="Limpiar búsqueda" aria-label="Limpiar búsqueda" onClick={() => setSearch("")}><X size={14} /></button>}</label>
              <label className="location-filter" title="Filtrar por ubicación"><MapPin size={14} /><select value={locationFilter} onChange={(event) => setLocationFilter(event.target.value as "all" | StorageLocation)} aria-label="Filtrar por ubicación"><option value="all">Ubicación</option><option value="pantry">Despensa</option><option value="refrigerator">Refrigerador</option><option value="freezer">Congelador</option></select><ChevronDown size={13} /></label>
            </div>
          </div>

          <div className="inventory-list-head"><span>Artículo</span><span>Ubicación</span><span>Cantidad</span><span>Caducidad</span><span>Estado</span><span className="sr-only">Acciones</span></div>
          <div className="inventory-list" aria-live="polite">
            {visibleItems.length ? visibleItems.map((item, index) => <article className={`inventory-row ${selectedId === item.id ? "row-selected" : ""}`} key={item.id} style={{ "--row-index": index } as CSSProperties} onClick={() => setSelectedId(selectedId === item.id ? null : item.id)}>
              <div className="product-cell"><span className={`product-mark product-${item.status}`}><span>{item.display_name.slice(0, 1).toLocaleUpperCase("es")}</span></span><span className="product-copy"><strong>{item.display_name}</strong><small>{item.ingredient_name ?? "Artículo libre"}</small></span></div>
              <span className="location-cell"><MapPin size={14} />{locationLabel(item.storage_location)}</span>
              <span className="quantity-cell"><strong>{item.quantity}</strong><small>{item.unit}</small></span>
              <span className="expiry-cell"><strong>{formatDate(item.expiration_date)}</strong><small>{dayMessage(item.days_remaining)}</small></span>
              <span className="status-cell"><StatusPill status={item.status} /></span>
              <button className="row-action" title={`Marcar ${item.display_name} como consumido`} aria-label={`Marcar ${item.display_name} como consumido`} disabled={item.status === "consumed"} onClick={(event) => { event.stopPropagation(); consumeFromRow(item); }}><Check size={15} /></button>
            </article>) : <div className="empty-state"><span className="empty-icon"><Package size={21} /></span><strong>No hay artículos en esta vista</strong><span>Ajusta los filtros o registra una compra.</span><button onClick={() => { setFilter("all"); setLocationFilter("all"); setSearch(""); }}>Limpiar filtros</button></div>}
          </div>

          <footer className="inventory-footer"><span>Mostrando <strong>{visibleItems.length}</strong> de <strong>{items.length}</strong> registros</span><span className="footer-updated"><span className={`footer-dot ${connection}`} />{connection === "live" ? "Actualizado desde PostgreSQL" : "Datos de demostración"}</span></footer>
          <div className="inventory-bottom-note"><span><CalendarDays size={14} /> Las fechas de caducidad se calculan en la base de datos.</span><span>HECHO PARA APROVECHAR MÁS <ArrowRight size={13} /></span></div>
        </section>
      </div>

      {connection === "demo" && <div className="demo-ribbon"><CloudOff size={13} /> Backend desconectado · cambios locales de demostración</div>}
      {toast && <div className="toast-message" role="status"><CircleCheck size={17} />{toast}<button onClick={() => setToast("")} title="Cerrar aviso" aria-label="Cerrar aviso"><X size={14} /></button></div>}
    </main>
  );
}

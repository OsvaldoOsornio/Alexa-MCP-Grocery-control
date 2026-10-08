export type StorageLocation = "pantry" | "refrigerator" | "freezer";
export type InventoryStatus =
  | "fresh"
  | "expiring_soon"
  | "expired"
  | "consumed"
  | "unknown";

export type InventoryItem = {
  id: number;
  user_id: number;
  display_name: string;
  ingredient_name: string | null;
  category: string | null;
  storage_location: StorageLocation;
  quantity: string;
  unit: string;
  is_opened: boolean;
  expiration_date: string | null;
  days_remaining: number | null;
  status: InventoryStatus;
};

export type InventoryStatusResponse = {
  user_id: number;
  count: number;
  items: InventoryItem[];
};

export type DemoEvent = {
  id: number;
  title: string;
  detail: string;
  time: string;
  kind: "receipt" | "opened" | "consumed" | "moved";
};

export const DEMO_USER_ID = 1;

function dateAfter(days: number, origin = new Date()): string {
  const date = new Date(origin.getTime());
  date.setHours(12, 0, 0, 0);
  date.setDate(date.getDate() + days);
  return date.toISOString().slice(0, 10);
}

function demoDateAfter(days: number): string {
  return dateAfter(days, new Date("2026-10-07T12:00:00"));
}

export function createDemoInventory(): InventoryItem[] {
  return [
    {
      id: 101,
      user_id: DEMO_USER_ID,
      display_name: "Tomates de rama",
      ingredient_name: "Tomate",
      category: "produce",
      storage_location: "refrigerator",
      quantity: "6.00",
      unit: "unidades",
      is_opened: false,
      expiration_date: demoDateAfter(2),
      days_remaining: 2,
      status: "expiring_soon",
    },
    {
      id: 102,
      user_id: DEMO_USER_ID,
      display_name: "Yogur natural",
      ingredient_name: "Yogur",
      category: "dairy",
      storage_location: "refrigerator",
      quantity: "4.00",
      unit: "unidades",
      is_opened: true,
      expiration_date: demoDateAfter(5),
      days_remaining: 5,
      status: "fresh",
    },
    {
      id: 103,
      user_id: DEMO_USER_ID,
      display_name: "Espinaca baby",
      ingredient_name: "Espinaca",
      category: "produce",
      storage_location: "refrigerator",
      quantity: "120.00",
      unit: "gramos",
      is_opened: true,
      expiration_date: demoDateAfter(-1),
      days_remaining: -1,
      status: "expired",
    },
    {
      id: 104,
      user_id: DEMO_USER_ID,
      display_name: "Huevos camperos",
      ingredient_name: "Huevos",
      category: "dairy",
      storage_location: "refrigerator",
      quantity: "10.00",
      unit: "unidades",
      is_opened: false,
      expiration_date: demoDateAfter(12),
      days_remaining: 12,
      status: "fresh",
    },
    {
      id: 105,
      user_id: DEMO_USER_ID,
      display_name: "Arroz basmati",
      ingredient_name: "Arroz",
      category: "pantry_staple",
      storage_location: "pantry",
      quantity: "750.00",
      unit: "gramos",
      is_opened: false,
      expiration_date: demoDateAfter(120),
      days_remaining: 120,
      status: "fresh",
    },
    {
      id: 106,
      user_id: DEMO_USER_ID,
      display_name: "Pan de masa madre",
      ingredient_name: "Pan",
      category: "bakery",
      storage_location: "pantry",
      quantity: "1.00",
      unit: "barra",
      is_opened: false,
      expiration_date: null,
      days_remaining: null,
      status: "unknown",
    },
    {
      id: 107,
      user_id: DEMO_USER_ID,
      display_name: "Pechuga de pollo",
      ingredient_name: "Pollo crudo",
      category: "meat_poultry",
      storage_location: "freezer",
      quantity: "450.00",
      unit: "gramos",
      is_opened: false,
      expiration_date: demoDateAfter(1),
      days_remaining: 1,
      status: "expiring_soon",
    },
    {
      id: 108,
      user_id: DEMO_USER_ID,
      display_name: "Mantequilla",
      ingredient_name: "Mantequilla",
      category: "dairy",
      storage_location: "refrigerator",
      quantity: "0.00",
      unit: "paquetes",
      is_opened: false,
      expiration_date: demoDateAfter(20),
      days_remaining: 20,
      status: "consumed",
    },
  ];
}

export function createDemoReceiptItems(startId: number): InventoryItem[] {
  return [
    {
      id: startId,
      user_id: DEMO_USER_ID,
      display_name: "Limones",
      ingredient_name: null,
      category: null,
      storage_location: "pantry",
      quantity: "4.00",
      unit: "unidades",
      is_opened: false,
      expiration_date: dateAfter(9),
      days_remaining: 9,
      status: "fresh",
    },
    {
      id: startId + 1,
      user_id: DEMO_USER_ID,
      display_name: "Garbanzos cocidos",
      ingredient_name: null,
      category: null,
      storage_location: "pantry",
      quantity: "2.00",
      unit: "botes",
      is_opened: false,
      expiration_date: dateAfter(30),
      days_remaining: 30,
      status: "fresh",
    },
  ];
}

export const initialDemoEvents: DemoEvent[] = [
  {
    id: 1,
    title: "Yogur marcado como abierto",
    detail: "Yogur natural · ayer, 18:42",
    time: "18:42",
    kind: "opened",
  },
  {
    id: 2,
    title: "Recibo procesado",
    detail: "Supermercado del barrio · lunes",
    time: "Lun",
    kind: "receipt",
  },
  {
    id: 3,
    title: "Pollo movido al congelador",
    detail: "Pechuga de pollo · lunes",
    time: "Lun",
    kind: "moved",
  },
];

export function formatDate(value: string | null): string {
  if (!value) return "Sin fecha";
  return new Intl.DateTimeFormat("es", {
    day: "numeric",
    month: "short",
  }).format(new Date(`${value}T12:00:00`));
}

export function statusLabel(status: InventoryStatus): string {
  const labels: Record<InventoryStatus, string> = {
    fresh: "En buen estado",
    expiring_soon: "Por vencer",
    expired: "Vencido",
    consumed: "Consumido",
    unknown: "Sin fecha",
  };
  return labels[status];
}

export function locationLabel(location: StorageLocation): string {
  const labels: Record<StorageLocation, string> = {
    pantry: "Despensa",
    refrigerator: "Refrigerador",
    freezer: "Congelador",
  };
  return labels[location];
}
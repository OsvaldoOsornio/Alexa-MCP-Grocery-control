// The five tools `app/tools/` registers on the MCP server. This union lives
// here rather than in mcp-client.ts so that client components can name a tool
// without importing the server-side transport module.
export type McpToolName =
  | "get_inventory_status"
  | "modify_item_state"
  | "ingest_receipt_items"
  | "update_pantry_context"
  | "generate_and_adapt_recipe";

// One turn of the voice exchange shown across the top of the Echo Show frame.
//
// `tool` is the identifier the MCP call was actually made with, so the strip
// cannot drift from what the server ran. `reply` is composed from that call's
// real response. `utterance` is the one scripted field: this machine has no
// microphone, so the wording is ours. The page says so in plain words on the
// developer bench rather than implying speech recognition it does not have.
export type VoiceTurn = {
  id: number;
  utterance: string;
  tool: McpToolName;
  reply: string;
  state: "working" | "answered" | "failed";
};

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

// Mirrors `app.models.enums.RipenessModifier`, the input vocabulary of
// `update_pantry_context`. It has no PostgreSQL counterpart, so this union is
// the only place the frontend pins the spelling.
export type RipenessModifier =
  | "very_ripe"
  | "ripe"
  | "underripe"
  | "smells_off"
  | "opened_long_ago";

// `update_pantry_context` answers either with the item it rewrote, or with a
// list of candidate names so a voice client can ask a follow-up question
// instead of guessing. Both arms arrive on the same payload.
export type PantryContextResponse = {
  success: boolean;
  error?: string;
  candidates?: string[];
  item?: {
    id: number;
    display_name: string;
    modifier: RipenessModifier;
    previous_expiration_date: string | null;
    expiration_date: string | null;
    days_remaining: number | null;
    discard_recommended: boolean;
  };
};

// What a person would actually say to produce each modifier. The device only
// ever sees the modifier; this map exists so the transcript can show the
// sentence the intent came from instead of the enum value.
//
// Every phrasing is built on a modal ("will need", "should", "must have") so
// that it stays grammatical whether the display name is singular or plural.
// Names come from the user's own pantry -- "Whole milk 1L" and "Vine tomatoes"
// go through the same template -- so the sentence cannot assume number.
export const RIPENESS_UTTERANCES: Record<RipenessModifier, (name: string) => string> = {
  underripe: (name) => `Alexa, the ${name} will need a few more days.`,
  ripe: (name) => `Alexa, the ${name} should be eaten soon.`,
  very_ripe: (name) => `Alexa, the ${name} should go today.`,
  smells_off: (name) => `Alexa, the ${name} must have gone off.`,
  opened_long_ago: (name) => `Alexa, I opened the ${name} a while back.`,
};

// Mirrors `app.services.recipe.Recipe`.
export type RecipeIngredient = {
  name: string;
  quantity: string;
  from_pantry: boolean;
};

export type Recipe = {
  title: string;
  servings: number;
  total_minutes: number;
  uses_expiring: string[];
  ingredients: RecipeIngredient[];
  steps: string[];
  missing: string[];
};

export type RecipeResponse = {
  success: boolean;
  error?: string;
  user_id: number;
  adapted?: boolean;
  excluded_items?: string[];
  // What the pantry said was urgent, independent of what the model chose.
  expiring_soon_in_pantry?: string[];
  recipe?: Recipe;
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

// Pinned to a fixed origin on purpose: this data seeds the initial React
// state, which renders on the server as well as the client, and a date
// derived from `new Date()` there would produce a hydration mismatch.
// The trade-off is that these demo dates drift from "today" over time.
function demoDateAfter(days: number): string {
  return dateAfter(days, new Date("2026-10-07T12:00:00"));
}

export function createDemoInventory(): InventoryItem[] {
  return [
    {
      id: 101,
      user_id: DEMO_USER_ID,
      display_name: "Vine tomatoes",
      ingredient_name: "Tomato",
      category: "produce",
      storage_location: "refrigerator",
      quantity: "6.00",
      unit: "units",
      is_opened: false,
      expiration_date: demoDateAfter(2),
      days_remaining: 2,
      status: "expiring_soon",
    },
    {
      id: 102,
      user_id: DEMO_USER_ID,
      display_name: "Plain yogurt",
      ingredient_name: "Plain yogurt",
      category: "dairy",
      storage_location: "refrigerator",
      quantity: "4.00",
      unit: "units",
      is_opened: true,
      expiration_date: demoDateAfter(5),
      days_remaining: 5,
      status: "fresh",
    },
    {
      id: 103,
      user_id: DEMO_USER_ID,
      display_name: "Baby spinach",
      ingredient_name: "Spinach",
      category: "produce",
      storage_location: "refrigerator",
      quantity: "120.00",
      unit: "grams",
      is_opened: true,
      expiration_date: demoDateAfter(-1),
      days_remaining: -1,
      status: "expired",
    },
    {
      id: 104,
      user_id: DEMO_USER_ID,
      display_name: "Free-range eggs",
      ingredient_name: "Eggs",
      category: "dairy",
      storage_location: "refrigerator",
      quantity: "10.00",
      unit: "units",
      is_opened: false,
      expiration_date: demoDateAfter(12),
      days_remaining: 12,
      status: "fresh",
    },
    {
      id: 105,
      user_id: DEMO_USER_ID,
      display_name: "Basmati rice",
      ingredient_name: "White rice",
      category: "pantry_staple",
      storage_location: "pantry",
      quantity: "750.00",
      unit: "grams",
      is_opened: false,
      expiration_date: demoDateAfter(120),
      days_remaining: 120,
      status: "fresh",
    },
    {
      id: 106,
      user_id: DEMO_USER_ID,
      display_name: "Sourdough loaf",
      ingredient_name: "Bread",
      category: "bakery",
      storage_location: "pantry",
      quantity: "1.00",
      unit: "loaf",
      is_opened: false,
      expiration_date: null,
      days_remaining: null,
      status: "unknown",
    },
    {
      id: 107,
      user_id: DEMO_USER_ID,
      display_name: "Chicken breast",
      ingredient_name: "Raw chicken (breast)",
      category: "meat_poultry",
      storage_location: "freezer",
      quantity: "450.00",
      unit: "grams",
      is_opened: false,
      expiration_date: demoDateAfter(1),
      days_remaining: 1,
      status: "expiring_soon",
    },
    {
      id: 108,
      user_id: DEMO_USER_ID,
      display_name: "Butter",
      ingredient_name: "Butter",
      category: "dairy",
      storage_location: "refrigerator",
      quantity: "0.00",
      unit: "packs",
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
      display_name: "Lemons",
      ingredient_name: null,
      category: null,
      storage_location: "pantry",
      quantity: "4.00",
      unit: "units",
      is_opened: false,
      expiration_date: dateAfter(9),
      days_remaining: 9,
      status: "fresh",
    },
    {
      id: startId + 1,
      user_id: DEMO_USER_ID,
      display_name: "Cooked chickpeas",
      ingredient_name: null,
      category: null,
      storage_location: "pantry",
      quantity: "2.00",
      unit: "cans",
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
    title: "Yogurt marked as opened",
    detail: "Plain yogurt · yesterday, 18:42",
    time: "18:42",
    kind: "opened",
  },
  {
    id: 2,
    title: "Receipt processed",
    detail: "Corner supermarket · Monday",
    time: "Mon",
    kind: "receipt",
  },
  {
    id: 3,
    title: "Chicken moved to the freezer",
    detail: "Chicken breast · Monday",
    time: "Mon",
    kind: "moved",
  },
];

export function formatDate(value: string | null): string {
  if (!value) return "No date";
  return new Intl.DateTimeFormat("en", {
    day: "numeric",
    month: "short",
  }).format(new Date(`${value}T12:00:00`));
}

export function statusLabel(status: InventoryStatus): string {
  const labels: Record<InventoryStatus, string> = {
    fresh: "Fresh",
    expiring_soon: "Expiring soon",
    expired: "Expired",
    consumed: "Consumed",
    unknown: "No date",
  };
  return labels[status];
}

// Most urgent first: expired, then whatever expires soonest, then items with
// no date at all. This is the order the Echo Show cards are chosen in, because
// an ambient screen gets one chance to show the right four things.
export function byUrgency(a: InventoryItem, b: InventoryItem): number {
  const rank = (item: InventoryItem) =>
    item.days_remaining === null ? Number.MAX_SAFE_INTEGER : item.days_remaining;
  return rank(a) - rank(b);
}

export function needsAttention(item: InventoryItem): boolean {
  return item.status === "expired" || item.status === "expiring_soon";
}

// Split into a numeral and a word so the card can set the numeral in display
// type and still keep the word that makes it unambiguous at two metres.
export function dayCountdown(days: number | null): { value: string; unit: string } {
  if (days === null) return { value: "--", unit: "no date on file" };
  if (days < 0) {
    const ago = Math.abs(days);
    return { value: String(ago), unit: ago === 1 ? "day past date" : "days past date" };
  }
  if (days === 0) return { value: "0", unit: "use it today" };
  return { value: String(days), unit: days === 1 ? "day left" : "days left" };
}

export function locationLabel(location: StorageLocation): string {
  const labels: Record<StorageLocation, string> = {
    pantry: "Pantry",
    refrigerator: "Refrigerator",
    freezer: "Freezer",
  };
  return labels[location];
}

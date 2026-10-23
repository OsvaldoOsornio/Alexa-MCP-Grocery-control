import { describe, expect, it } from "vitest";
import { createDemoInventory, spokenAttention, type InventoryItem } from "@/lib/kitchen-data";

const base = createDemoInventory()[0];

function item(display_name: string, status: InventoryItem["status"], days_remaining: number): InventoryItem {
  return { ...base, display_name, status, days_remaining };
}

describe("spokenAttention", () => {
  it("never tells you to eat something past its date", () => {
    expect(spokenAttention([
      item("Vine tomatoes", "expiring_soon", 2),
      item("Chicken breast", "expired", -1),
    ])).toBe("Vine tomatoes need eating. Chicken breast is past its date, throw it out.");
  });

  it("agrees the verb with a singular name and with pairs", () => {
    expect(spokenAttention([item("Plain yogurt", "expiring_soon", 1)]))
      .toBe("Plain yogurt needs eating.");
    expect(spokenAttention([
      item("Baby spinach", "expired", -2),
      item("Lemons", "expired", -1),
    ])).toBe("Baby spinach and Lemons are past their date, throw them out.");
  });

  it("counts and leads with the most urgent when there are more than two", () => {
    expect(spokenAttention([
      item("Butter", "expiring_soon", 3),
      item("Plain yogurt", "expiring_soon", 1),
      item("Vine tomatoes", "expiring_soon", 2),
    ])).toBe("3 things need eating, starting with Plain yogurt and Vine tomatoes.");
  });

  it("says the pantry is fine when nothing is urgent", () => {
    expect(spokenAttention([item("Basmati rice", "fresh", 200)]))
      .toBe("Nothing needs eating today. The pantry is fine.");
  });
});

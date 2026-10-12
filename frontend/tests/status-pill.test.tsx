import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StatusPill } from "@/components/status-pill";
import type { InventoryStatus } from "@/lib/kitchen-data";

const colorClasses: Record<InventoryStatus, string> = {
  fresh: "status-fresh",
  expiring_soon: "status-expiring_soon",
  expired: "status-expired",
  consumed: "status-consumed",
  unknown: "status-unknown",
};

describe("StatusPill traffic light", () => {
  it.each([
    ["fresh", "Fresh"],
    ["expiring_soon", "Expiring soon"],
    ["expired", "Expired"],
    ["consumed", "Consumed"],
    ["unknown", "No date"],
  ] as const)("applies the colour and label for %s", (status, label) => {
    render(<StatusPill status={status} />);

    const indicator = screen.getByRole("status", { name: label });
    expect(indicator).toHaveClass("status-pill", colorClasses[status]);
    expect(indicator.querySelector(".status-dot")).toBeInTheDocument();
  });

  it("changes the colour class when the status changes", () => {
    const { rerender } = render(<StatusPill status="fresh" />);
    const freshIndicator = screen.getByRole("status", { name: "Fresh" });

    expect(freshIndicator).toHaveClass("status-fresh");

    rerender(<StatusPill status="expired" />);

    const expiredIndicator = screen.getByRole("status", { name: "Expired" });
    expect(expiredIndicator).toHaveClass("status-expired");
    expect(expiredIndicator).not.toHaveClass("status-fresh");
  });
});
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

describe("StatusPill semáforo", () => {
  it.each([
    ["fresh", "En buen estado"],
    ["expiring_soon", "Por vencer"],
    ["expired", "Vencido"],
    ["consumed", "Consumido"],
    ["unknown", "Sin fecha"],
  ] as const)("aplica color y etiqueta para %s", (status, label) => {
    render(<StatusPill status={status} />);

    const indicator = screen.getByRole("status", { name: label });
    expect(indicator).toHaveClass("status-pill", colorClasses[status]);
    expect(indicator.querySelector(".status-dot")).toBeInTheDocument();
  });

  it("cambia la clase de color al cambiar de estado", () => {
    const { rerender } = render(<StatusPill status="fresh" />);
    const freshIndicator = screen.getByRole("status", { name: "En buen estado" });

    expect(freshIndicator).toHaveClass("status-fresh");

    rerender(<StatusPill status="expired" />);

    const expiredIndicator = screen.getByRole("status", { name: "Vencido" });
    expect(expiredIndicator).toHaveClass("status-expired");
    expect(expiredIndicator).not.toHaveClass("status-fresh");
  });
});
import { statusLabel, type InventoryStatus } from "@/lib/kitchen-data";

type StatusPillProps = {
  status: InventoryStatus;
};

export function StatusPill({ status }: StatusPillProps) {
  return (
    <span className={`status-pill status-${status}`} role="status" aria-label={statusLabel(status)}>
      <span className="status-dot" aria-hidden="true" />
      {statusLabel(status)}
    </span>
  );
}
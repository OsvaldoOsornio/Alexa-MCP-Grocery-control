import { Refrigerator, Package, Snowflake } from "lucide-react";
import { StatusPill } from "@/components/status-pill";
import {
  dayCountdown, locationLabel,
  type InventoryItem, type StorageLocation,
} from "@/lib/kitchen-data";

function LocationMark({ where }: { where: StorageLocation }) {
  if (where === "freezer") return <Snowflake size={18} />;
  if (where === "refrigerator") return <Refrigerator size={18} />;
  return <Package size={18} />;
}

/**
 * One pantry item, sized to be read across a kitchen rather than clicked.
 *
 * Status is carried by the border and background tint *and* by the StatusPill's
 * word, so the card still reads correctly without colour vision. Nothing here
 * is interactive: on an ambient screen the card is an answer, not a control.
 */
export function ItemCard({ item }: { item: InventoryItem }) {
  const countdown = dayCountdown(item.days_remaining);

  return (
    <article className={`show-card card-${item.status}`}>
      <StatusPill status={item.status} />
      <h3 className="show-card-name">{item.display_name}</h3>
      <p className="show-card-count">
        <strong>{countdown.value}</strong>
        <span>{countdown.unit}</span>
      </p>
      <p className="show-card-where">
        <LocationMark where={item.storage_location} />
        {locationLabel(item.storage_location)}
        <span className="show-card-qty">
          {item.quantity} {item.unit}
        </span>
      </p>
    </article>
  );
}

/**
 * Fills the fourth grid cell. It reports only what is *not* already a card:
 * the overflow when the pantry holds more than fits, and otherwise the size of
 * the pantry itself. It must never restate a number the cards beside it
 * already show, and it is never a placeholder -- both numbers are real.
 */
export function RestOfKitchenCard({
  hidden, tracked,
}: { hidden: number; tracked: number }) {
  return (
    <article className="show-card card-rest">
      {hidden > 0 ? (
        <>
          <h3 className="show-card-name">Rest of the pantry</h3>
          <p className="show-card-count">
            <strong>{hidden}</strong>
            <span>{hidden === 1 ? "more item, less urgent" : "more items, less urgent"}</span>
          </p>
        </>
      ) : (
        <>
          <h3 className="show-card-name">That is the whole pantry</h3>
          <p className="show-card-count">
            <strong>{tracked}</strong>
            <span>{tracked === 1 ? "item tracked" : "items tracked"}</span>
          </p>
        </>
      )}
      <p className="show-card-where">Ask for any of it by name.</p>
    </article>
  );
}

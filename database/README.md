# Esquema de base de datos — Inventario de cocina zero-waste

## Diagrama entidad-relación

```mermaid
erDiagram
    USERS ||--o{ PANTRY_INVENTORY : "posee"
    SHELF_LIFE_RULES ||--o{ PANTRY_INVENTORY : "cataloga"

    USERS {
        bigint id PK
        varchar email
    }

    SHELF_LIFE_RULES {
        bigint id PK
        varchar ingredient_name UK
        enum category
        enum default_storage
        smallint shelf_life_days_unopened
        numeric open_shelf_life_multiplier
        smallint frozen_shelf_life_days
        boolean requires_refrigeration_after_opening
    }

    PANTRY_INVENTORY {
        bigint id PK
        bigint user_id FK
        bigint shelf_life_rule_id FK
        varchar display_name
        numeric quantity
        varchar unit
        enum storage_location
        boolean is_opened
        date purchase_date
        date opened_date
        date custom_expiration_date
        date expiration_date "calculado por trigger"
        boolean is_consumed
    }
```

## Relaciones

- **`pantry_inventory.user_id` → `users.id`** (`ON DELETE CASCADE`): si se borra un usuario, se borra su inventario.
- **`pantry_inventory.shelf_life_rule_id` → `shelf_life_rules.id`** (`ON DELETE SET NULL`): el catálogo es la fuente de la regla de caducidad, pero borrar una regla no debe borrar el stock del usuario; simplemente el ítem queda "sin catalogar" y depende de `custom_expiration_date`.

Es una relación clásica **catálogo (1) — inventario (N)**: `shelf_life_rules` es de solo lectura/administración (semilla + mantenimiento), `pantry_inventory` es transaccional (crece con cada compra del usuario).

## Lógica de caducidad (trigger `calculate_pantry_expiration`)

Orden de prioridad al calcular `expiration_date`:

1. `custom_expiration_date` (el usuario la fijó manualmente, p. ej. la fecha impresa en el empaque) → siempre gana.
2. Si está en `freezer` y la regla define `frozen_shelf_life_days` → `purchase_date + frozen_shelf_life_days`.
3. Si `is_opened = TRUE` → `opened_date + ROUND(shelf_life_days_unopened * open_shelf_life_multiplier)`.
4. Si no → `purchase_date + shelf_life_days_unopened`.
5. Sin regla ni fecha manual → no se puede calcular (`NULL` en insert, se conserva el valor previo en update).

Esto se recalcula automáticamente en cada `INSERT`/`UPDATE` de `pantry_inventory` (por ejemplo, al marcar `is_opened = TRUE`), así que la app nunca tiene que replicar esta lógica de fechas en el backend — solo leerla.

## Orden de ejecución

```bash
psql -d tu_base -f database/schema.sql
psql -d tu_base -f database/seed_shelf_life_rules.sql
```

> **Nota sobre `users`:** la tabla incluida en `schema.sql` es un *stub* mínimo para que las FKs sean válidas de forma autónoma. Si tu proyecto ya tiene autenticación (Cognito, Supabase, Auth0, etc.), elimina ese bloque y ajusta el tipo de `pantry_inventory.user_id` para que coincida con tu PK real (p. ej. `UUID`).

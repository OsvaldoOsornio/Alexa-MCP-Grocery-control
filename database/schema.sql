-- =============================================================================
-- Zero-Waste Kitchen Inventory — PostgreSQL Schema
-- =============================================================================
-- Tablas:
--   1. shelf_life_rules  -> catálogo maestro de caducidad por ingrediente
--   2. pantry_inventory  -> stock real de cada usuario, enlazado al catálogo
--
-- Relación: pantry_inventory.shelf_life_rule_id  ->  shelf_life_rules.id  (N:1)
--           pantry_inventory.user_id             ->  users.id            (N:1)
--
-- NOTA: `users` se incluye aquí como stub mínimo para que las FKs sean
-- válidas y el script sea ejecutable de forma autónoma. Si tu app ya tiene
-- una tabla de usuarios (Cognito/Auth0/Supabase/etc.), BORRA este bloque y
-- ajusta el tipo de `pantry_inventory.user_id` para que coincida con tu PK
-- real (p. ej. UUID en vez de BIGINT).
-- =============================================================================

BEGIN;

-- -----------------------------------------------------------------------------
-- 0. Tipos ENUM reutilizables
-- -----------------------------------------------------------------------------
DO $$ BEGIN
    CREATE TYPE ingredient_category AS ENUM (
        'produce',            -- frutas y verduras frescas
        'dairy',               -- lácteos y huevos
        'meat_poultry',        -- carnes y aves
        'seafood',             -- pescados y mariscos
        'bakery',              -- panadería
        'pantry_staple',       -- básicos de despensa (arroz, pasta, harina...)
        'condiment_sauce',     -- aceites, salsas, condimentos
        'beverage',            -- bebidas
        'frozen',              -- productos ya congelados de fábrica
        'other'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE storage_location AS ENUM (
        'pantry',
        'refrigerator',
        'freezer'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- -----------------------------------------------------------------------------
-- 0.1 Stub de usuarios (eliminar/ajustar si ya existe en tu sistema)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email      VARCHAR(255) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- -----------------------------------------------------------------------------
-- 1. shelf_life_rules — catálogo maestro de caducidad
-- -----------------------------------------------------------------------------
CREATE TABLE shelf_life_rules (
    id                                    BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    -- Nombre canónico del ingrediente (español, en minúsculas por convención de la app)
    ingredient_name                       VARCHAR(100) NOT NULL,

    category                              ingredient_category NOT NULL,

    -- Dónde se guarda este ingrediente por defecto mientras está SIN abrir
    default_storage                       storage_location NOT NULL,

    -- Días de vida útil desde la compra, SIN ABRIR, en `default_storage`
    shelf_life_days_unopened              SMALLINT NOT NULL,

    -- Multiplicador aplicado a `shelf_life_days_unopened` una vez ABIERTO.
    -- Ej: 0.50 => una vez abierto, dura la mitad de días (desde la fecha de apertura).
    -- 1.00 => abrirlo no acorta su vida útil (ej. azúcar, arroz seco).
    open_shelf_life_multiplier            NUMERIC(3, 2) NOT NULL DEFAULT 1.00,

    -- Días de vida útil si se congela (NULL = congelar no es recomendable/aplicable)
    frozen_shelf_life_days                SMALLINT,

    -- Si TRUE, una vez abierto debe refrigerarse aunque su almacenamiento
    -- por defecto (unopened) sea la despensa (ej. mayonesa, aceite de oliva no, ketchup sí)
    requires_refrigeration_after_opening  BOOLEAN NOT NULL DEFAULT FALSE,

    notes                                 TEXT,

    created_at                            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                            TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_shelf_life_rules_ingredient_name UNIQUE (ingredient_name),
    CONSTRAINT ck_shelf_life_rules_unopened_positive
        CHECK (shelf_life_days_unopened > 0),
    CONSTRAINT ck_shelf_life_rules_multiplier_range
        CHECK (open_shelf_life_multiplier > 0 AND open_shelf_life_multiplier <= 1),
    CONSTRAINT ck_shelf_life_rules_frozen_positive
        CHECK (frozen_shelf_life_days IS NULL OR frozen_shelf_life_days > 0)
);

COMMENT ON TABLE shelf_life_rules IS
    'Catálogo maestro: días de caducidad por defecto por ingrediente, con multiplicador al abrir.';

CREATE INDEX ix_shelf_life_rules_category ON shelf_life_rules (category);

-- -----------------------------------------------------------------------------
-- 2. pantry_inventory — stock actual del usuario
-- -----------------------------------------------------------------------------
CREATE TABLE pantry_inventory (
    id                       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    user_id                  BIGINT NOT NULL
                                 REFERENCES users (id) ON DELETE CASCADE,

    -- Referencia al catálogo. Puede ser NULL si el ingrediente no está
    -- catalogado todavía (item "libre"); en ese caso, `custom_expiration_date`
    -- es la única fuente de verdad para la caducidad.
    shelf_life_rule_id       BIGINT
                                 REFERENCES shelf_life_rules (id) ON DELETE SET NULL,

    -- Nombre mostrado al usuario (puede incluir marca, ej. "Leche entera Alqueria")
    display_name             VARCHAR(150) NOT NULL,

    quantity                 NUMERIC(10, 2) NOT NULL DEFAULT 1,
    unit                     VARCHAR(20)    NOT NULL DEFAULT 'unidad',

    storage_location         storage_location NOT NULL DEFAULT 'pantry',

    is_opened                BOOLEAN NOT NULL DEFAULT FALSE,
    purchase_date            DATE    NOT NULL DEFAULT CURRENT_DATE,
    opened_date              DATE,

    -- Permite al usuario forzar una fecha exacta (ej. la impresa en el empaque),
    -- que siempre tiene prioridad sobre el cálculo automático.
    custom_expiration_date   DATE,

    -- Calculado automáticamente por el trigger `trg_calc_pantry_expiration`
    -- (ver más abajo). No se debe escribir manualmente salvo en migraciones.
    expiration_date          DATE,

    is_consumed               BOOLEAN     NOT NULL DEFAULT FALSE,
    consumed_at                TIMESTAMPTZ,

    notes                    TEXT,

    created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at               TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT ck_pantry_inventory_quantity_non_negative
        CHECK (quantity >= 0),
    CONSTRAINT ck_pantry_inventory_opened_after_purchase
        CHECK (opened_date IS NULL OR opened_date >= purchase_date),
    CONSTRAINT ck_pantry_inventory_opened_requires_date
        CHECK (is_opened = FALSE OR opened_date IS NOT NULL),
    CONSTRAINT ck_pantry_inventory_consumed_consistency
        CHECK (consumed_at IS NULL OR is_consumed = TRUE)
);

COMMENT ON TABLE pantry_inventory IS
    'Stock actual de despensa/refrigerador/congelador por usuario.';

CREATE INDEX ix_pantry_inventory_user_id ON pantry_inventory (user_id);
CREATE INDEX ix_pantry_inventory_shelf_life_rule_id ON pantry_inventory (shelf_life_rule_id);

-- Índice parcial: la consulta más frecuente de una app zero-waste es
-- "qué tiene el usuario X que esté por vencer, sin contar lo ya consumido".
CREATE INDEX ix_pantry_inventory_user_expiration_active
    ON pantry_inventory (user_id, expiration_date)
    WHERE is_consumed = FALSE;

-- -----------------------------------------------------------------------------
-- 3. Triggers
-- -----------------------------------------------------------------------------

-- 3.1 updated_at genérico, reutilizable en cualquier tabla con esa columna
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_shelf_life_rules_set_updated_at
    BEFORE UPDATE ON shelf_life_rules
    FOR EACH ROW
    EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER trg_pantry_inventory_set_updated_at
    BEFORE UPDATE ON pantry_inventory
    FOR EACH ROW
    EXECUTE FUNCTION set_updated_at();

-- 3.2 Cálculo automático de expiration_date en pantry_inventory
--
-- Prioridad:
--   1) custom_expiration_date, si el usuario la definió manualmente.
--   2) Si storage_location = 'freezer' y el catálogo define frozen_shelf_life_days:
--        purchase_date + frozen_shelf_life_days
--   3) Si is_opened = TRUE (con opened_date):
--        opened_date + ROUND(shelf_life_days_unopened * open_shelf_life_multiplier)
--   4) En otro caso (sin abrir):
--        purchase_date + shelf_life_days_unopened
--   5) Si no hay shelf_life_rule_id ni custom_expiration_date, no se puede
--      calcular: se conserva el valor previo (UPDATE) o queda NULL (INSERT).
CREATE OR REPLACE FUNCTION calculate_pantry_expiration()
RETURNS TRIGGER AS $$
DECLARE
    rule shelf_life_rules%ROWTYPE;
    opened_days SMALLINT;
BEGIN
    IF NEW.custom_expiration_date IS NOT NULL THEN
        NEW.expiration_date := NEW.custom_expiration_date;
        RETURN NEW;
    END IF;

    IF NEW.shelf_life_rule_id IS NULL THEN
        IF TG_OP = 'INSERT' THEN
            NEW.expiration_date := NULL;
        ELSE
            NEW.expiration_date := OLD.expiration_date;
        END IF;
        RETURN NEW;
    END IF;

    SELECT * INTO rule FROM shelf_life_rules WHERE id = NEW.shelf_life_rule_id;

    IF NOT FOUND THEN
        NEW.expiration_date := NULL;
        RETURN NEW;
    END IF;

    IF NEW.storage_location = 'freezer' AND rule.frozen_shelf_life_days IS NOT NULL THEN
        NEW.expiration_date := NEW.purchase_date + rule.frozen_shelf_life_days;
    ELSIF NEW.is_opened AND NEW.opened_date IS NOT NULL THEN
        opened_days := GREATEST(
            1,
            ROUND(rule.shelf_life_days_unopened * rule.open_shelf_life_multiplier)
        );
        NEW.expiration_date := NEW.opened_date + opened_days;
    ELSE
        NEW.expiration_date := NEW.purchase_date + rule.shelf_life_days_unopened;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_pantry_inventory_calc_expiration
    BEFORE INSERT OR UPDATE ON pantry_inventory
    FOR EACH ROW
    EXECUTE FUNCTION calculate_pantry_expiration();

-- -----------------------------------------------------------------------------
-- 4. Vista de conveniencia para el dashboard "zero-waste"
-- -----------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_pantry_inventory_status AS
SELECT
    pi.id,
    pi.user_id,
    pi.display_name,
    sr.ingredient_name,
    sr.category,
    pi.storage_location,
    pi.quantity,
    pi.unit,
    pi.is_opened,
    pi.expiration_date,
    (pi.expiration_date - CURRENT_DATE) AS days_remaining,
    CASE
        WHEN pi.is_consumed THEN 'consumed'
        WHEN pi.expiration_date IS NULL THEN 'unknown'
        WHEN pi.expiration_date < CURRENT_DATE THEN 'expired'
        WHEN pi.expiration_date <= CURRENT_DATE + INTERVAL '2 days' THEN 'expiring_soon'
        ELSE 'fresh'
    END AS status
FROM pantry_inventory pi
LEFT JOIN shelf_life_rules sr ON sr.id = pi.shelf_life_rule_id;

COMMIT;

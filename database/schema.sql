-- =============================================================================
-- Zero-Waste Kitchen Inventory - PostgreSQL Schema
-- =============================================================================
-- Tables:
--   1. shelf_life_rules  -> master expiry catalog, one row per ingredient
--   2. pantry_inventory  -> each user's real stock, linked to the catalog
--
-- Relations: pantry_inventory.shelf_life_rule_id  ->  shelf_life_rules.id  (N:1)
--            pantry_inventory.user_id             ->  users.id            (N:1)
--
-- NOTE: `users` is included here as a minimal stub so the foreign keys are
-- valid and the script runs standalone. If your app already has a users table
-- (Cognito/Auth0/Supabase/etc.), DELETE this block and change the type of
-- `pantry_inventory.user_id` to match your real primary key (for example
-- UUID instead of BIGINT).
-- =============================================================================

BEGIN;

-- -----------------------------------------------------------------------------
-- 0. Reusable ENUM types
-- -----------------------------------------------------------------------------
DO $$ BEGIN
    CREATE TYPE ingredient_category AS ENUM (
        'produce',            -- fresh fruit and vegetables
        'dairy',               -- dairy and eggs
        'meat_poultry',        -- meat and poultry
        'seafood',             -- fish and shellfish
        'bakery',              -- bakery
        'pantry_staple',       -- pantry staples (rice, pasta, flour...)
        'condiment_sauce',     -- oils, sauces, condiments
        'beverage',            -- drinks
        'frozen',              -- products frozen at the factory
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
-- 0.1 Users stub (delete or adjust if your system already has one)
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    email      VARCHAR(255) NOT NULL UNIQUE,
    created_at TIMESTAMPTZ  NOT NULL DEFAULT now()
);

-- -----------------------------------------------------------------------------
-- 1. shelf_life_rules - master expiry catalog
-- -----------------------------------------------------------------------------
CREATE TABLE shelf_life_rules (
    id                                    BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    -- Canonical ingredient name (the app's convention is lower case)
    ingredient_name                       VARCHAR(100) NOT NULL,

    category                              ingredient_category NOT NULL,

    -- Where this ingredient is stored by default while UNOPENED
    default_storage                       storage_location NOT NULL,

    -- Shelf life in days from purchase, UNOPENED, in `default_storage`
    shelf_life_days_unopened              SMALLINT NOT NULL,

    -- Multiplier applied to `shelf_life_days_unopened` once OPENED.
    -- e.g. 0.50 => once opened it lasts half as many days (from the opened date).
    -- 1.00 => opening it does not shorten its life (e.g. sugar, dry rice).
    open_shelf_life_multiplier            NUMERIC(3, 2) NOT NULL DEFAULT 1.00,

    -- Shelf life in days if frozen (NULL = freezing is not advisable/applicable)
    frozen_shelf_life_days                SMALLINT,

    -- If TRUE, it must be refrigerated once opened even when its default
    -- (unopened) storage is the pantry (e.g. mayonnaise and ketchup yes,
    -- olive oil no)
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
    'Master catalog: default shelf life in days per ingredient, with an opened multiplier.';

CREATE INDEX ix_shelf_life_rules_category ON shelf_life_rules (category);

-- -----------------------------------------------------------------------------
-- 2. pantry_inventory - the user's current stock
-- -----------------------------------------------------------------------------
CREATE TABLE pantry_inventory (
    id                       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    user_id                  BIGINT NOT NULL
                                 REFERENCES users (id) ON DELETE CASCADE,

    -- Reference to the catalog. May be NULL when the ingredient is not
    -- catalogued yet (a "free" item); in that case `custom_expiration_date`
    -- is the only source of truth for the expiry.
    shelf_life_rule_id       BIGINT
                                 REFERENCES shelf_life_rules (id) ON DELETE SET NULL,

    -- Name shown to the user (may include a brand, e.g. "Alqueria whole milk")
    display_name             VARCHAR(150) NOT NULL,

    quantity                 NUMERIC(10, 2) NOT NULL DEFAULT 1,
    unit                     VARCHAR(20)    NOT NULL DEFAULT 'unit',

    storage_location         storage_location NOT NULL DEFAULT 'pantry',

    is_opened                BOOLEAN NOT NULL DEFAULT FALSE,
    purchase_date            DATE    NOT NULL DEFAULT CURRENT_DATE,
    opened_date              DATE,

    -- Lets the user force an exact date (e.g. the one printed on the pack),
    -- which always takes priority over the automatic calculation.
    custom_expiration_date   DATE,

    -- Calculated automatically by the `trg_calc_pantry_expiration` trigger
    -- (see below). Do not write it by hand except in migrations.
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
    'Current pantry/refrigerator/freezer stock per user.';

CREATE INDEX ix_pantry_inventory_user_id ON pantry_inventory (user_id);
CREATE INDEX ix_pantry_inventory_shelf_life_rule_id ON pantry_inventory (shelf_life_rule_id);

-- Partial index: the most frequent query in a zero-waste app is
-- "what does user X have that is about to expire, excluding what is consumed".
CREATE INDEX ix_pantry_inventory_user_expiration_active
    ON pantry_inventory (user_id, expiration_date)
    WHERE is_consumed = FALSE;

-- -----------------------------------------------------------------------------
-- 3. Triggers
-- -----------------------------------------------------------------------------

-- 3.1 Generic updated_at, reusable on any table with that column
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

-- 3.2 Automatic calculation of expiration_date on pantry_inventory
--
-- Priority:
--   1) custom_expiration_date, if the user set it manually.
--   2) If storage_location = 'freezer' and the catalog defines
--      frozen_shelf_life_days:
--        purchase_date + frozen_shelf_life_days
--   3) If is_opened = TRUE (with opened_date):
--        opened_date + ROUND(shelf_life_days_unopened * open_shelf_life_multiplier)
--   4) Otherwise (unopened):
--        purchase_date + shelf_life_days_unopened
--   5) With neither shelf_life_rule_id nor custom_expiration_date it cannot
--      be calculated: the previous value is kept (UPDATE) or left NULL (INSERT).
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
-- 4. Convenience view for the "zero-waste" dashboard
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

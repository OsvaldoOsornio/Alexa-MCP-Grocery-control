-- =============================================================================
-- Seed data: ~15 common ingredients for shelf_life_rules
-- =============================================================================
-- Values are based on general food-safety guidance (FDA FoodKeeper / USDA)
-- used as an industry reference; adjust them for your local market.
--
-- Run after database/schema.sql
-- =============================================================================

INSERT INTO shelf_life_rules
    (ingredient_name, category, default_storage, shelf_life_days_unopened,
     open_shelf_life_multiplier, frozen_shelf_life_days, requires_refrigeration_after_opening, notes)
VALUES
    -- Dairy and eggs
    ('Whole milk',                'dairy',           'refrigerator', 10,  0.70, 90,  FALSE,
     'Keeps ~7 days refrigerated once opened. Freezing changes the texture, so use it for cooking only.'),
    ('Eggs',                      'dairy',           'refrigerator', 30,  1.00, NULL, FALSE,
     'There is no "opened" state; eat within a month of purchase.'),
    ('Plain yogurt',              'dairy',           'refrigerator', 14,  0.50, NULL, TRUE,
     'Freezing is not recommended because the texture separates.'),
    ('Butter',                    'dairy',           'refrigerator', 60,  0.50, 180, FALSE, NULL),
    ('Hard cheese (parmesan)',    'dairy',           'refrigerator', 180, 0.33, 240, TRUE, NULL),

    -- Bakery
    ('Sliced bread',              'bakery',          'pantry',       7,   0.57, 90,  FALSE,
     'Once opened, close the bag tightly to stop it drying out or going mouldy.'),

    -- Dry pantry staples
    ('White rice',                'pantry_staple',   'pantry',       730, 0.70, NULL, FALSE, NULL),
    ('Dried pasta',               'pantry_staple',   'pantry',       730, 0.50, NULL, FALSE, NULL),
    ('Wheat flour',               'pantry_staple',   'pantry',       365, 0.50, NULL, FALSE,
     'Store in an airtight container once opened to keep out pests and moisture.'),
    ('Sugar',                     'pantry_staple',   'pantry',       1095,1.00, NULL, FALSE,
     'Keeps almost indefinitely while dry; 3 years is used here as a conservative reference.'),

    -- Condiments and sauces
    ('Olive oil',                 'condiment_sauce', 'pantry',       545, 0.33, NULL, FALSE, NULL),
    ('Mayonnaise',                'condiment_sauce', 'pantry',       365, 0.16, NULL, TRUE,
     'Refrigerate immediately after opening.'),

    -- Meat
    ('Raw chicken (breast)',      'meat_poultry',    'refrigerator', 2,   1.00, 270, FALSE,
     'Eat quickly when fresh; freeze to extend the usable life significantly.'),
    ('Packaged cooked ham',       'meat_poultry',    'refrigerator', 30,  0.16, 60,  FALSE,
     'Vacuum-packed and unopened; once opened, eat within a few days.'),

    -- Produce
    ('Tomato',                    'produce',         'pantry',       7,   0.43, NULL, TRUE,
     'Once cut, refrigerate and eat within 2-3 days.')
ON CONFLICT (ingredient_name) DO NOTHING;

-- =============================================================================
-- Seed data: ~15 ingredientes comunes para shelf_life_rules
-- =============================================================================
-- Valores basados en guías generales de inocuidad alimentaria (FDA FoodKeeper /
-- USDA) usadas como referencia de la industria; ajústalos a tu mercado local.
--
-- Ejecutar después de database/schema.sql
-- =============================================================================

INSERT INTO shelf_life_rules
    (ingredient_name, category, default_storage, shelf_life_days_unopened,
     open_shelf_life_multiplier, frozen_shelf_life_days, requires_refrigeration_after_opening, notes)
VALUES
    -- Lácteos y huevos
    ('Leche entera',              'dairy',           'refrigerator', 10,  0.70, 90,  FALSE,
     'Abierta dura ~7 días refrigerada. Congelar cambia textura, usar solo para cocinar.'),
    ('Huevos',                    'dairy',           'refrigerator', 30,  1.00, NULL, FALSE,
     'No aplica concepto de "abierto"; consumir dentro del mes desde compra.'),
    ('Yogur natural',             'dairy',           'refrigerator', 14,  0.50, NULL, TRUE,
     'No se recomienda congelar por separación de la textura.'),
    ('Mantequilla',               'dairy',           'refrigerator', 60,  0.50, 180, FALSE, NULL),
    ('Queso duro (parmesano)',    'dairy',           'refrigerator', 180, 0.33, 240, TRUE, NULL),

    -- Panadería
    ('Pan de molde',              'bakery',          'pantry',       7,   0.57, 90,  FALSE,
     'Una vez abierto, cerrar bien la bolsa para evitar que se seque/enmohezca.'),

    -- Básicos de despensa (secos)
    ('Arroz blanco',              'pantry_staple',   'pantry',       730, 0.70, NULL, FALSE, NULL),
    ('Pasta seca',                'pantry_staple',   'pantry',       730, 0.50, NULL, FALSE, NULL),
    ('Harina de trigo',           'pantry_staple',   'pantry',       365, 0.50, NULL, FALSE,
     'Guardar en recipiente hermético una vez abierta para evitar plagas y humedad.'),
    ('Azúcar',                    'pantry_staple',   'pantry',       1095,1.00, NULL, FALSE,
     'Prácticamente indefinida si se mantiene seca; se usa 3 años como referencia conservadora.'),

    -- Condimentos y salsas
    ('Aceite de oliva',           'condiment_sauce', 'pantry',       545, 0.33, NULL, FALSE, NULL),
    ('Mayonesa',                  'condiment_sauce', 'pantry',       365, 0.16, NULL, TRUE,
     'Refrigerar inmediatamente después de abrir.'),

    -- Carnes
    ('Pollo crudo (pechuga)',     'meat_poultry',    'refrigerator', 2,   1.00, 270, FALSE,
     'Consumir rápido en fresco; congelar para extender significativamente la vida útil.'),
    ('Jamón cocido envasado',     'meat_poultry',    'refrigerator', 30,  0.16, 60,  FALSE,
     'Envasado al vacío sin abrir; una vez abierto consumir en pocos días.'),

    -- Frutas y verduras
    ('Tomate',                    'produce',         'pantry',       7,   0.43, NULL, TRUE,
     'Una vez cortado, refrigerar y consumir en 2-3 días.')
ON CONFLICT (ingredient_name) DO NOTHING;

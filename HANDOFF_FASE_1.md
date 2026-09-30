# Handoff Fase 1 → Fase 2 (Servidor MCP en Python)

Estado: **Fase 1 completa y verificada.** 54 tests pasando, 0 fallando, 3 omitidos (requieren un Postgres real, ver más abajo). Este documento resume lo construido para que el desarrollo del servidor MCP (Fase 2, según `Claude.md`) arranque sin tener que releer todo el código.

## 1. Qué existe en el repo

```
database/
  schema.sql                  -- DDL completo: ENUMs, tablas, constraints, índices, triggers, vista
  seed_shelf_life_rules.sql   -- 15 ingredientes precargados
  README.md                   -- diagrama ER (mermaid) y explicación del trigger de caducidad
app/
  core/
    config.py                 -- Settings (pydantic-settings) ya leyendo .env — ver §6
  db/
    session.py                -- engine async (SQLAlchemy) + get_session() — ya scaffoldeado, ver §6
  models/                     -- SQLAlchemy 2.0 (ORM)
    enums.py                  -- IngredientCategory, StorageLocation (compartidos con Pydantic)
    base.py                   -- Base declarativa + TimestampMixin (created_at/updated_at)
    shelf_life_rule.py        -- modelo ShelfLifeRule
    pantry_inventory.py       -- modelo PantryInventory
  schemas/                    -- Pydantic v2 (I/O de API)
    shelf_life_rule.py        -- ShelfLifeRuleCreate/Update/Read
    pantry_inventory.py       -- PantryInventoryCreate/Update/Read
  services/                   -- stub vacío: lógica de negocio / integraciones (Bedrock, etc.)
  tools/                      -- stub vacío: tools MCP expuestas por el servidor
  main.py                     -- entry point stub del servidor MCP (FastMCP, streamable-http)
tests/                        -- pytest, todos nuevos en esta fase (ver §5)
.env.example                  -- ya existe, ver §6
requirements.txt              -- lista completa del proyecto (todas las fases); ver §4 qué está instalado hoy
pytest.ini                    -- pythonpath=. , testpaths=tests
```

`app/core/config.py`, `app/db/session.py`, `app/main.py`, `.env.example`, `app/services/`, `app/tools/` **ya existían** antes de esta fase de QA (scaffold de arranque para Fase 2) — no los toqué ni los testeé, se documentan aquí solo para que no se dupliquen. Lo único nuevo/verificado en esta fase de QA es `tests/`, este handoff, y dos fixes en `app/models/` (ver §7).

**IMPORTANTE — fuente de verdad de la DDL:** `database/schema.sql` es la única fuente de verdad del esquema (tipos ENUM, constraints, triggers). Los modelos SQLAlchemy **describen** esa estructura para el ORM, pero no la generan: los ENUM se declaran con `create_type=False` a propósito, así que `Base.metadata.create_all()` **no** crea los tipos `ingredient_category` / `storage_location` ni los triggers. Antes de que el servidor MCP toque la base de datos, hay que ejecutar:

```bash
psql -d tu_base -f database/schema.sql
psql -d tu_base -f database/seed_shelf_life_rules.sql
```

## 2. Estructura de las tablas

### `shelf_life_rules` (catálogo maestro, ~solo lectura en runtime)

| Columna | Tipo | Notas |
|---|---|---|
| `id` | BIGINT (identity) | PK |
| `ingredient_name` | VARCHAR(100) | **UNIQUE** |
| `category` | ENUM `ingredient_category` | produce, dairy, meat_poultry, seafood, bakery, pantry_staple, condiment_sauce, beverage, frozen, other |
| `default_storage` | ENUM `storage_location` | pantry, refrigerator, freezer |
| `shelf_life_days_unopened` | SMALLINT | días de vida sin abrir, desde la compra |
| `open_shelf_life_multiplier` | NUMERIC(3,2), default 1.00 | multiplicador sobre lo anterior una vez abierto (0 < x ≤ 1) |
| `frozen_shelf_life_days` | SMALLINT NULL | si se congela |
| `requires_refrigeration_after_opening` | BOOLEAN | ej. mayonesa, tomate cortado |
| `notes`, `created_at`, `updated_at` | | |

15 filas ya cargadas (leche, huevos, yogur, mantequilla, queso, pan, arroz, pasta, harina, azúcar, aceite de oliva, mayonesa, pollo crudo, jamón cocido, tomate).

### `pantry_inventory` (stock real del usuario, transaccional)

| Columna | Tipo | Notas |
|---|---|---|
| `id` | BIGINT (identity) | PK |
| `user_id` | BIGINT | FK → `users.id`, `ON DELETE CASCADE` |
| `shelf_life_rule_id` | BIGINT NULL | FK → `shelf_life_rules.id`, `ON DELETE SET NULL` (ítem "libre" si es NULL) |
| `display_name` | VARCHAR(150) | nombre mostrado al usuario |
| `quantity` | NUMERIC(10,2), default 1 | ≥ 0 |
| `unit` | VARCHAR(20), default 'unidad' | |
| `storage_location` | ENUM `storage_location`, default 'pantry' | |
| `is_opened` | BOOLEAN | si es TRUE, `opened_date` es obligatoria (constraint) |
| `purchase_date` | DATE | default `CURRENT_DATE` en DB — **pero ver gotcha #3** |
| `opened_date` | DATE NULL | debe ser ≥ `purchase_date` |
| `custom_expiration_date` | DATE NULL | fijada manualmente por el usuario; siempre gana |
| `expiration_date` | DATE NULL | **calculada por trigger, nunca por la app** (ver §3) |
| `is_consumed`, `consumed_at` | | para tracking zero-waste |

**`users`** es un stub mínimo (`id BIGINT`, `email`) definido solo en `schema.sql`, no es un modelo ORM en `app/models`. Si Fase 2/3 conecta un sistema de auth real con otra PK (ej. UUID), hay que actualizar el tipo de `user_id` en `app/models/pantry_inventory.py` y en `schema.sql`.

## 3. Lógica de caducidad (trigger, no Python)

`calculate_pantry_expiration()` (en `schema.sql`) recalcula `expiration_date` en cada INSERT/UPDATE de `pantry_inventory`, con esta prioridad: `custom_expiration_date` > congelado (`frozen_shelf_life_days`) > abierto (`opened_date + round(shelf_life_days_unopened * open_shelf_life_multiplier)`) > sin abrir (`purchase_date + shelf_life_days_unopened`).

El modelo `PantryInventory.expiration_date` está marcado con `server_default=FetchedValue()` / `server_onupdate=FetchedValue()`, así que SQLAlchemy la re-lee automáticamente vía `RETURNING` tras cada `commit()`/`refresh()`. **El servidor MCP nunca debe escribir `expiration_date` manualmente** — solo `is_opened`, `opened_date`, `storage_location`, etc., y dejar que la DB la recalcule.

Hay una vista de conveniencia `v_pantry_inventory_status` (en `schema.sql`) con `days_remaining` y `status` (`fresh` / `expiring_soon` / `expired` / `consumed` / `unknown`) — útil directamente para la tool `get_inventory_status()` descrita en `Claude.md`.

## 4. Dependencias

`requirements.txt` ya lista **todo el proyecto** (todas las fases), no solo Fase 1:
```
fastapi
uvicorn[standard]
mcp
sqlalchemy>=2.0
asyncpg
pydantic>=2.0
pydantic-settings
boto3
python-dotenv
pytest
pytest-asyncio
httpx
```

**Ojo:** en el entorno donde corrí esta fase de QA, solo instalé y verifiqué lo mínimo necesario para los tests de modelos (`SQLAlchemy==2.1.1`, `pydantic==2.13.4`, `pytest==9.1.0` — ninguno pineado en el archivo, se deja el rango abierto que ya estaba). El resto de paquetes del `requirements.txt` (`fastapi`, `mcp`, `asyncpg`, `pydantic-settings`, `boto3`, `python-dotenv`, `pytest-asyncio`, `httpx`) **no están instalados todavía** en ese entorno — el agente de Backend va a necesitar correr `pip install -r requirements.txt` de verdad antes de poder levantar `app/main.py` o conectar `app/db/session.py` a Postgres. El driver de Postgres ya decidido en el scaffold es **`asyncpg`** (vía `postgresql+asyncpg://...`) con `SQLAlchemy` async (`create_async_engine`/`AsyncSession`) — no hace falta agregar `psycopg`.

## 5. Tests (`tests/`)

```
pip install -r requirements.txt
pytest -v
```

(Para solo correr los tests de modelos sin instalar todo el stack de Fase 2/3, basta con `pip install sqlalchemy pydantic pytest` — es todo lo que estos tests usan; ver nota del §4 sobre qué está realmente instalado.)

Resultado actual: **54 passed, 3 skipped**.

- `test_models_metadata.py` — introspección de estructura (columnas, FKs, ondelete) sin necesitar DB.
- `test_shelf_life_rule_model.py`, `test_pantry_inventory_model.py` — CRUD y constraints vía SQLite en memoria (rápido, sin Postgres).
- `test_schemas_shelf_life_rule.py`, `test_schemas_pantry_inventory.py` — validación Pydantic (rangos, campos obligatorios condicionales, computed field).
- `test_integration_postgres.py` — **se salta automáticamente** salvo que exista la env var `TEST_DATABASE_URL`. Es la única forma de probar el trigger real de Postgres (SQLite no tiene triggers PL/pgSQL). Instrucciones para correrlo están en el docstring del archivo.

## 6. Variables de entorno

`.env.example` ya existe en la raíz del repo (del scaffold previo a esta fase de QA):

```
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/zero_waste_sous_chef
AWS_REGION=us-east-1
BEDROCK_MODEL_ID=anthropic.claude-3-5-sonnet-20241022-v2:0
MCP_SERVER_NAME=zero-waste-sous-chef
MCP_SERVER_HOST=0.0.0.0
MCP_SERVER_PORT=8000
```

Y `app/core/config.py` ya las consume vía `pydantic-settings` (`Settings.database_url`, `.aws_region`, `.bedrock_model_id`, `.mcp_server_name/host/port`, con `env_file=".env"`). **Ojo:** `DATABASE_URL` de ejemplo usa el driver `postgresql+asyncpg://` (no `+psycopg`), consistente con `app/db/session.py`, que ya usa `create_async_engine`/`AsyncSession`. Todo esto es anterior a mi trabajo de QA; lo dejo documentado para que no se reintroduzca o se contradiga.

Una variable adicional, propia de esta fase de QA:

| Variable | Usada por | Estado |
|---|---|---|
| `TEST_DATABASE_URL` | `tests/test_integration_postgres.py` (opcional) | Nueva, agregada en esta fase. Formato: `postgresql+psycopg://user:pass@host:5432/db_test` (usa el driver **sync** `psycopg`, no `asyncpg`, porque esos tests usan `Session` síncrono de SQLAlchemy contra los modelos, igual que el resto de la suite — ver §5). Sin ella, esos 3 tests se saltan. Requiere que `schema.sql` + el seed ya estén aplicados en esa base de datos de prueba. |

Nada de AWS/Bedrock se ejercita todavía en código (esas env vars solo están declaradas en `.env.example`/`config.py` a la espera de Fase 3).

## 7. Gotchas encontrados y corregidos en QA (para no reintroducirlos)

1. **FK sin tipo explícito → `NullType()`.** `user_id`/`shelf_life_rule_id`/`id` ahora declaran `BigInteger` explícito. Causa: SQLAlchemy infiere el tipo de una columna FK del tipo de la columna referenciada *si esa tabla ya está registrada en el mismo `MetaData`*; como `users` no es un modelo ORM propio, quedaba sin resolver y la DDL fallaba al compilar. Si agregan un modelo `User` real, no rompe nada, pero no quiten el tipo explícito.
2. **`server_default="false"` (string plano) ≠ `FALSE` (keyword SQL).** Se compila como el literal `'false'` citado. Postgres lo castea implícitamente bien, pero es frágil (y rompe en SQLite, usado en tests). Ya está corregido a `server_default=sqlalchemy.false()` en los 3 booleanos (`is_opened`, `is_consumed`, `requires_refrigeration_after_opening`). **Convención para nuevas columnas booleanas: usar siempre `sqlalchemy.true()`/`false()`, nunca strings.**
3. **`purchase_date` con `server_default=CURRENT_DATE` es UTC, no el reloj local de la app.** Puede diferir en ±1 día del `date.today()` de Python cerca de medianoche UTC. La capa de API (`PantryInventoryCreate.purchase_date`, con `default_factory=date.today`) ya evita depender de este default en el flujo normal — trátenlo solo como respaldo para inserts SQL directos, nunca asuman que coincide con la fecha "de hoy" calculada en Python.
4. **`id` es `BigInteger` en Postgres pero `Integer` en SQLite** (`.with_variant(Integer, "sqlite")`) — necesario porque SQLite solo autoincrementa su alias de `rowid` con el tipo exacto `INTEGER PRIMARY KEY`. Es solo un detalle de testing; en Postgres siempre compila a `BIGINT`, igual que `schema.sql`.

## 8. Siguiente paso (Fase 2, según `Claude.md`)

Servidor MCP en Python (transporte Streamable HTTP) exponiendo `get_inventory_status()`, `add_items_from_text_or_image()`, `modify_item_state()`, `generate_and_adapt_recipe()`. El scaffold de arranque **ya existe** (`app/main.py` con `FastMCP(...).run(transport="streamable-http")`, `app/core/config.py`, `app/db/session.py` async) — el trabajo de Fase 2 es:

1. `pip install -r requirements.txt` (instalar de verdad `fastapi`, `mcp`, `asyncpg`, `pydantic-settings`, etc., que hoy no están instalados en el entorno de esta fase de QA).
2. Correr `database/schema.sql` + `database/seed_shelf_life_rules.sql` contra el Postgres real apuntado por `DATABASE_URL`.
3. Implementar las 4 tools en `app/tools/` (stub vacío), usando `app.db.session.get_session()` para la conexión y `app.models` / `app.schemas` (ya validados en esta fase) para leer/escribir — sin redefinir tipos ni recalcular `expiration_date` a mano (eso lo hace el trigger, §3).
4. Registrar esas tools en `mcp` (`app/main.py`) y agregar tests de integración (con `pytest-asyncio`, ya en `requirements.txt`) que sí toquen un Postgres real, siguiendo el mismo patrón que `tests/test_integration_postgres.py`.

# Handoff Fase 3: contrato de datos para Frontend

## Conexión MCP

El servidor ofrece MCP por Streamable HTTP en `http://<host>:<puerto>/mcp` (por defecto `http://localhost:8000/mcp`) y negocia la revisión `2025-11-25`. No hay rutas REST por herramienta: el cliente debe inicializar una sesión MCP, enviar `notifications/initialized`, consultar `tools/list` y usar `tools/call`. Las llamadas posteriores a `initialize` incluyen el header `Mcp-Session-Id`.

Tools disponibles: `get_inventory_status`, `modify_item_state` e `ingest_receipt_items`.

## Inventario consultable

### `get_inventory_status`

Argumentos MCP:

```json
{
  "user_id": 17,
  "include_consumed": false
}
```

`user_id` es requerido. `include_consumed` es opcional y por defecto `false`.

Forma de `structuredContent`:

```json
{
  "user_id": 17,
  "count": 1,
  "items": [
    {
      "id": 42,
      "user_id": 17,
      "display_name": "Leche entera",
      "ingredient_name": "Leche entera",
      "category": "dairy",
      "storage_location": "refrigerator",
      "quantity": "1.50",
      "unit": "litros",
      "is_opened": false,
      "expiration_date": "2026-10-17",
      "days_remaining": 10,
      "status": "fresh"
    }
  ]
}
```

`items` procede de `v_pantry_inventory_status`. `quantity` se serializa como string decimal; `expiration_date` es `YYYY-MM-DD` o `null`. `category` puede ser `null` para artículos libres. `status` es uno de `fresh`, `expiring_soon`, `expired`, `consumed` o `unknown`.

## Cambiar estado de un artículo

### `modify_item_state`

Argumentos MCP: `user_id` y `item_id` son obligatorios. Enviar uno o más de estos campos opcionales: `is_opened` (boolean), `opened_date` (fecha ISO), `storage_location` (`pantry`, `refrigerator`, `freezer`) e `is_consumed` (boolean).

```json
{
  "user_id": 17,
  "item_id": 42,
  "is_opened": true,
  "opened_date": "2026-10-07",
  "storage_location": "refrigerator",
  "is_consumed": false
}
```

La respuesta exitosa contiene `success: true` e `item` con `id`, `user_id`, `display_name`, `storage_location`, `is_opened`, `opened_date`, `is_consumed`, `consumed_at` y `expiration_date`. Fechas y timestamps se serializan en ISO 8601. Si no se encuentra el artículo para ese usuario, devuelve `success: false` y `error`.

## Ingestar foto de recibo

### `ingest_receipt_items`

Argumentos MCP:

```json
{
  "user_id": 17,
  "image_base64": "<base64 sin prefijo data URL>",
  "media_type": "image/jpeg"
}
```

`user_id` e `image_base64` son obligatorios. `media_type` es opcional (default `image/jpeg`); formatos aceptados: `image/jpeg`, `image/png`, `image/gif`, `image/webp`. El tamaño decodificado máximo es 5 MB. El Frontend debe enviar el Base64 puro, sin `data:image/...;base64,`.

Respuesta exitosa:

```json
{
  "success": true,
  "user_id": 17,
  "count": 1,
  "items": [
    {
      "id": 43,
      "display_name": "Leche entera",
      "quantity": "2.00",
      "unit": "litros",
      "shelf_life_rule_id": 8,
      "storage_location": "refrigerator",
      "expiration_date": "2026-10-17"
    }
  ]
}
```

`items` puede ser una lista vacía si no se extrajeron productos. La respuesta de esta tool es un resumen de los registros insertados; para obtener estados y `days_remaining`, llamar después a `get_inventory_status`.

## Modelo final y semántica

El almacenamiento `pantry_inventory` contiene `id`, `user_id`, `shelf_life_rule_id` (nullable), `display_name`, `quantity`, `unit`, `storage_location`, `is_opened`, `purchase_date`, `opened_date` (nullable), `custom_expiration_date` (nullable), `expiration_date` (nullable), `is_consumed`, `consumed_at` (nullable) y `notes` (nullable). Los IDs son enteros; `quantity` es decimal y en las respuestas MCP se representa como string.

Bedrock extrae internamente líneas con `display_name`, `ingredient_name`, `quantity` y `unit`. `ingredient_name` se asocia al catálogo `shelf_life_rules` sin distinguir mayúsculas/minúsculas. Si hay coincidencia, el registro recibe su `shelf_life_rule_id` y `default_storage`; si no, queda como artículo libre con `shelf_life_rule_id: null` y `storage_location: "pantry"`.

El Frontend no debe calcular ni enviar `expiration_date`. PostgreSQL la asigna con el trigger durante la escritura y la aplicación la lee después de `refresh`. Si no hay regla de vida útil, puede quedar `null`; el estado correspondiente de la vista es `unknown`. Para registros con regla, la fecha deriva de la regla, la ubicación, las fechas de compra/apertura y cualquier fecha de vencimiento manual.

## Errores y requisitos de entorno

Las validaciones de imagen y la respuesta no válida de Bedrock producen un error de tool MCP. Para ejecutar ingestión se requieren credenciales AWS reconocidas por boto3, acceso a Amazon Bedrock en `AWS_REGION` y el model ID configurado (por defecto Claude 3.5 Sonnet). La base PostgreSQL debe tener aplicados `database/schema.sql` y `database/seed_shelf_life_rules.sql`.

`user_id` todavía no se vincula a una identidad autenticada en el servidor. No debe considerarse una frontera de autorización si el cliente está expuesto a usuarios no confiables.

## Verificación QA

El test mockeado de ingestión está en `tests/test_inventory_service.py`. Simula la respuesta JSON de Bedrock y el `refresh` de la sesión; verifica el parseo, la selección de regla/ubicación y la serialización de la caducidad asignada por el servidor. No sustituye un test con PostgreSQL real, que es el que valida el trigger; los tests de integración existentes requieren `TEST_DATABASE_URL`.
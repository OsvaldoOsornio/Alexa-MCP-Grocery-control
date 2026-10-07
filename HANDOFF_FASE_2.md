# Handoff Fase 2: servidor MCP

## Resumen

El servidor MCP de Zero-Waste Sous-Chef usa el SDK oficial de Python (`mcp>=1.24,<2`) y transporte **Streamable HTTP**. La versión verificada es `mcp 1.30.0`; negocia la revisión del protocolo `2025-11-25`.

La app y el registro de las tools están en `app/main.py`. Las tools expuestas actualmente son `get_inventory_status` y `modify_item_state`, registradas en `app/tools/inventory.py`; sus operaciones de datos están en `app/services/inventory.py`.

## Transporte y métodos MCP

- URL local por defecto: `http://localhost:8000/mcp`.
- `POST /mcp`: initialize, notificaciones, `tools/list` y `tools/call` como mensajes JSON-RPC 2.0. El cliente debe aceptar `application/json` y `text/event-stream`.
- `GET /mcp`: canal opcional de eventos del servidor para una sesión Streamable HTTP.
- `DELETE /mcp`: termina la sesión del protocolo.
- La negociación crea una sesión; las solicitudes posteriores deben incluir el header `Mcp-Session-Id` recibido en `initialize`.

Ejemplo de inicialización:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "initialize",
  "params": {
    "protocolVersion": "2025-11-25",
    "capabilities": {},
    "clientInfo": {"name": "mi-cliente", "version": "1.0"}
  }
}
```

Luego el cliente envía `notifications/initialized`, consulta `tools/list` y ejecuta las tools con `tools/call`. No son rutas REST individuales para cada herramienta.

## Tools y payloads

### `get_inventory_status`

Argumentos aceptados:

```json
{
  "user_id": 17,
  "include_consumed": false
}
```

`user_id` es obligatorio e integer. `include_consumed` es opcional, booleano y por defecto `false`. La respuesta contiene `user_id`, `count` e `items`; cada elemento incluye `id`, `display_name`, `ingredient_name`, `category`, `storage_location`, `quantity`, `unit`, `is_opened`, `expiration_date`, `days_remaining` y `status`. `quantity` se serializa como decimal en texto y las fechas como ISO 8601. Los estados vienen de `v_pantry_inventory_status` (`fresh`, `expiring_soon`, `expired`, `consumed`, `unknown`).

### `modify_item_state`

Argumentos aceptados:

```json
{
  "user_id": 17,
  "item_id": 42,
  "is_opened": true,
  "opened_date": "2026-10-07",
  "storage_location": "freezer",
  "is_consumed": false
}
```

`user_id` y `item_id` son obligatorios e integer. Los demás campos son opcionales: `is_opened` e `is_consumed` son booleanos; `opened_date` es una fecha ISO `YYYY-MM-DD`; `storage_location` admite `pantry`, `refrigerator` o `freezer`. Se debe proporcionar al menos un campo de estado. `opened_date` requiere `is_opened: true`; al abrir sin fecha se usa la fecha actual, y al cerrar se limpia `opened_date`. Marcar consumido registra `consumed_at`; revertirlo la limpia.

La respuesta de éxito es `{"success": true, "item": ...}`. Si el artículo no pertenece al `user_id` indicado o no existe, la tool devuelve `{"success": false, "error": ...}`. Las fechas de caducidad nunca las calcula ni escribe la aplicación: las recalcula el trigger PostgreSQL.

Ejemplo de llamada JSON-RPC:

```json
{
  "jsonrpc": "2.0",
  "id": 2,
  "method": "tools/call",
  "params": {
    "name": "get_inventory_status",
    "arguments": {"user_id": 17}
  }
}
```

## Configuración e inicio

Instala dependencias y arranca desde la raíz del repositorio:

```powershell
venv\Scripts\python.exe -m pip install -r requirements.txt
venv\Scripts\python.exe -m app.main
```

El comando alternativo con el Python activo es `python -m app.main`. La configuración lee `.env`: `DATABASE_URL`, `MCP_SERVER_HOST` (por defecto `0.0.0.0`), `MCP_SERVER_PORT` (por defecto `8000`) y `MCP_SERVER_NAME`. `DATABASE_URL` debe usar `postgresql+asyncpg://...`.

Antes de invocar tools, la base debe tener aplicado `database/schema.sql` y `database/seed_shelf_life_rules.sql`. La vista y el trigger son parte de ese esquema.

## Pruebas

```powershell
venv\Scripts\python.exe -m pytest -q
```

`tests/test_mcp_streamable_http.py` negocia el protocolo por ASGI/HTTP, verifica la sesión, lista schemas y realiza las dos llamadas MCP con la capa de base de datos simulada. No requiere PostgreSQL. Los tests de integración del trigger se omiten salvo que se configure `TEST_DATABASE_URL`.

## Límites conocidos y continuación

El servidor todavía no autentica clientes. `user_id` llega en el payload y sirve para limitar la consulta, pero no prueba la identidad del llamante; no debe exponerse a una red no confiable sin incorporar autenticación/autorización.

Las tools de alta de artículos y generación/adaptación de recetas siguen pendientes. La base de datos real y sus migraciones/seed también deben configurarse por entorno.
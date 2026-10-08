# Handoff Fase 4: QA del semáforo y arquitectura

## Ejecutar el frontend

Desde el directorio `frontend/`, con Node.js 24 LTS:

```powershell
npm ci
npm run dev
```

Abre `http://localhost:3000`. El Route Handler usa por defecto `http://127.0.0.1:8000/mcp`; para otro destino copia `frontend/.env.example` a `frontend/.env.local` y cambia `MCP_URL`. Sin backend, la cocina muestra el inventario demo y permite simular eventos localmente.

## Verificación y build

```powershell
npm run lint
npm test
npm run build
npm start
```

`npm run build` genera el bundle de producción. `npm start` sirve ese bundle en modo producción después de construirlo. `npm run test:watch` ejecuta Vitest en modo interactivo.

Las pruebas de color están en `frontend/tests/status-pill.test.tsx`. React Testing Library renderiza el indicador para los cinco estados, comprueba la etiqueta y la clase semántica de color, y hace `rerender` de `fresh` a `expired` para validar que cambia la tonalidad aplicada. Los colores concretos están definidos por `.status-*` en `frontend/app/globals.css`; el test verifica que el componente selecciona la clase vinculada a esos estilos.

## Arquitectura

### Frontend (`frontend/`)

- `app/page.tsx`: workspace interactivo de cocina, simulador de eventos, resumen, búsqueda, filtros y filas de inventario. Consulta el backend al inicio; si no responde, usa fixtures tipados del modo demo.
- `app/globals.css`: tokens visuales, colores del semáforo y breakpoints responsive.
- `app/layout.tsx`: layout raíz, fuentes optimizadas por Next y metadata.
- `app/api/mcp/route.ts`: proxy server-side con allowlist de tools; evita que el navegador llame directamente al endpoint MCP.
- `lib/mcp-client.ts`: cliente JSON-RPC Streamable HTTP: initialize, notificación de inicialización, `tools/call` y cierre de sesión.
- `lib/kitchen-data.ts`: tipos que reflejan `v_pantry_inventory_status`, fixtures y utilidades de fechas/etiquetas.
- `components/status-pill.tsx`: indicador accesible de estado; combina `status-pill` con la clase específica `status-${status}`.
- `tests/status-pill.test.tsx`, `tests/setup.ts`, `vitest.config.mts`: Vitest + JSDOM + React Testing Library.

### Backend Python (`app/`)

- `app/main.py`: FastMCP sobre Streamable HTTP, protocolo `2025-11-25`.
- `app/tools/inventory.py`: tools `get_inventory_status`, `modify_item_state` e `ingest_receipt_items`.
- `app/services/inventory.py`: lectura y modificación SQLAlchemy async, parsing de recibos con Bedrock y mapeo al catálogo.
- `app/db/session.py`, `app/models/`, `app/schemas/`: sesión, entidades y validación Pydantic.
- `database/schema.sql`: esquema PostgreSQL, vista `v_pantry_inventory_status` y trigger que calcula `expiration_date`.

El frontend invoca las tools MCP mediante `/api/mcp`; no consume rutas REST directas del backend. La expiración viene calculada por PostgreSQL y no debe derivarse en React.

## Clases del semáforo

| Estado backend | Clase React/CSS | Color visual |
|---|---|---|
| `fresh` | `status-fresh` | Verde |
| `expiring_soon` | `status-expiring_soon` | Ámbar |
| `expired` | `status-expired` | Coral |
| `consumed` | `status-consumed` | Gris verdoso |
| `unknown` | `status-unknown` | Azul grisáceo |

La clase se deriva directamente de `status`; `null` en `expiration_date` no se convierte en una fecha inventada: la vista entrega `unknown`.

## Integración y límites

El frontend usa `user_id: 1` como usuario de demo y el backend todavía no tiene autenticación. Configura `MCP_URL` en el entorno del servidor Next, no en variables públicas `NEXT_PUBLIC_*`. Para datos reales se requiere backend activo, PostgreSQL preparado con `database/schema.sql` y el seed, y credenciales AWS si se procesa una foto de recibo.
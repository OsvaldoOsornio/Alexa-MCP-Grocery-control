# Despensa Viva

UI React/Next.js para simular eventos de cocina y revisar el semáforo del inventario.

## Iniciar

Desde este directorio:

```powershell
npm install
npm run dev
```

Abre `http://localhost:3000`. El inventario demo y los eventos locales se habilitan automáticamente cuando el servidor MCP no responde.

## Conectar el backend

Copia `.env.example` a `.env.local` y ajusta `MCP_URL` si el servidor MCP no está en `http://127.0.0.1:8000/mcp`. El Route Handler `/api/mcp` negocia una sesión Streamable HTTP y llama las tools autorizadas. La interfaz consume `get_inventory_status`, `modify_item_state` e `ingest_receipt_items` según el contrato de `../HANDOFF_FASE_3.md`.

El frontend usa por defecto `user_id: 1`, un identificador de demostración. El backend todavía no autentica al usuario, por lo que este valor no constituye autorización.

# Guion técnico: Despensa Viva

**Duración total:** 2:30 (150 segundos)  
**Formato:** captura de pantalla 16:9, narración en español, música ligera sin competir con la voz.  
**Preparación:** para mostrar llamadas reales, iniciar PostgreSQL, aplicar esquema y seed, levantar MCP y Next, y confirmar credenciales/permisos de Bedrock. Si Bedrock no está disponible, identificar el modo demo en pantalla y no presentarlo como OCR real.

| Tiempo | Acción Visual | Audio |
|---|---|---|
| 00:00–00:12 | Apertura sobre la UI de cocina. Paneo breve desde “Simulador de eventos” hasta el semáforo; se ven estados verde, ámbar y coral. | **Voz:** “¿Y si la cocina te avisara qué usar primero? Despensa Viva convierte cada compra y cada cambio de estado en un inventario claro para reducir desperdicio.” **Audio:** base rítmica cálida, baja. |
| 00:12–00:30 | Mostrar el indicador de conexión. Si MCP está apagado, dejar visible “Modo demo”; filtrar “Por vencer” y buscar un ingrediente. | **Voz:** “La interfaz funciona también como simulador: filtra por estado o ubicación y explora datos locales cuando el backend no está disponible. El modo demo se identifica siempre; no finge persistencia.” **Audio:** clics suaves sincronizados con los filtros. |
| 00:30–00:50 | Cambiar a “Estado”, seleccionar un producto y simular “Consumir”. El contador baja, el artículo pasa al filtro de consumidos y aparece el evento reciente. | **Voz:** “Al consumir un producto, React actualiza el semáforo y el registro. Con MCP conectado, esa misma acción se envía mediante `modify_item_state` y la lista se vuelve a consultar.” **Audio:** confirmación sutil al aplicar. |
| 00:50–01:12 | Sobreimpresión del flujo `Browser → Next.js /api/mcp → FastMCP`. Mostrar brevemente `initialize`, `notifications/initialized` y `tools/call` con protocolo `2025-11-25`. | **Voz:** “El navegador no habla directamente con la base de datos. Un Route Handler de Next actúa como proxy y abre una sesión Streamable HTTP con FastMCP. Así, el frontend consume tools, no endpoints REST inventados.” **Audio:** transición breve al aparecer el diagrama. |
| 01:12–01:35 | En “Recibo”, cargar una fotografía de recibo real. Mostrar el archivo codificado como Base64 entrando a `ingest_receipt_items`; no mostrar credenciales ni variables secretas. | **Voz:** “Para una compra nueva, la foto se valida y viaja como Base64 por la tool `ingest_receipt_items`. Boto3 llama a Amazon Bedrock Converse con Claude 3.5 Sonnet para extraer nombre, cantidad y unidad.” **Audio:** sonido discreto de escaneo, sin efectos de ciencia ficción. |
| 01:35–01:57 | Mostrar una respuesta estructurada de ejemplo; resaltar coincidencia de un ingrediente con `shelf_life_rules`. Luego enseñar la inserción en `pantry_inventory`. | **Voz:** “La respuesta estructurada se valida antes de guardarla. Si el ingrediente coincide con el catálogo, hereda su regla y ubicación; si no, queda como artículo libre en despensa. El recibo no decide la fecha de caducidad.” **Audio:** música continúa, baja. |
| 01:57–02:18 | Diagrama corto PostgreSQL: insert/update → trigger → `expiration_date` → vista de estado. Volver a la UI y refrescar inventario; aparece la fecha y su estado. | **Voz:** “PostgreSQL mantiene la fuente de verdad: un trigger calcula `expiration_date`, y la vista `v_pantry_inventory_status` entrega días restantes y el semáforo. La UI presenta ese resultado, sin duplicar reglas en JavaScript.” **Audio:** clic al sincronizar. |
| 02:18–02:30 | Pantalla final con README, comandos `npm test` y `npm run build`; cierre con logo/nombre del proyecto y URL local. | **Voz:** “Despensa Viva: React, MCP, Bedrock y PostgreSQL trabajando en una sola cocina. Revisa el README para iniciar, probar y contribuir.” **Audio:** cierre musical de dos segundos. |

## Notas de grabación

- Grabar con el badge `MCP en vivo` solo si las llamadas reales están funcionando; el estado inicial se comprueba con `get_inventory_status`.
- No mostrar `AWS_ACCESS_KEY_ID`, secretos, `.env`, datos personales ni recibos con información identificable.
- La demo de transición de color puede mostrarse localmente, pero para demostrar persistencia hay que confirmar la respuesta MCP y la consulta posterior.
- Mantener visibles las etiquetas de estado además del color para que el semáforo sea comprensible y accesible.
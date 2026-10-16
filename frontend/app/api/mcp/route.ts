import { callMcpTool, type McpToolName } from "@/lib/mcp-client";

// The full tool surface the MCP server exposes. The Echo Show screen drives
// all five, so the allow-list is no longer a subset: it exists to reject
// anything a tampered client body asks for that the server does not define.
const allowedTools = new Set<McpToolName>([
  "get_inventory_status",
  "modify_item_state",
  "ingest_receipt_items",
  "update_pantry_context",
  "generate_and_adapt_recipe",
]);

export async function POST(request: Request) {
  let body: { tool?: string; arguments?: unknown };
  try {
    body = (await request.json()) as { tool?: string; arguments?: unknown };
  } catch {
    return Response.json({ error: "The body must be valid JSON." }, { status: 400 });
  }

  if (!body.tool || !allowedTools.has(body.tool as McpToolName)) {
    return Response.json({ error: "MCP tool not allowed." }, { status: 400 });
  }
  if (
    !body.arguments ||
    typeof body.arguments !== "object" ||
    Array.isArray(body.arguments)
  ) {
    return Response.json({ error: "arguments must be a JSON object." }, { status: 400 });
  }

  try {
    const data = await callMcpTool(
      body.tool as McpToolName,
      body.arguments as Record<string, unknown>,
    );
    return Response.json({ data, source: "mcp" });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Could not connect to the MCP server.";
    return Response.json({ error: message }, { status: 503 });
  }
}
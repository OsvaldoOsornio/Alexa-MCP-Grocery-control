const MCP_PROTOCOL_VERSION = "2025-11-25";
const ACCEPT_HEADER = "application/json, text/event-stream";

type JsonRpcPayload = {
  error?: { message?: string };
  result?: {
    isError?: boolean;
    structuredContent?: unknown;
    content?: Array<{ text?: string }>;
  };
};

export type McpToolName =
  | "get_inventory_status"
  | "modify_item_state"
  | "ingest_receipt_items"
  | "update_pantry_context"
  | "generate_and_adapt_recipe";

async function readRpcResponse(response: Response): Promise<JsonRpcPayload> {
  const body = await response.text();
  if (response.headers.get("content-type")?.includes("application/json")) {
    return JSON.parse(body) as JsonRpcPayload;
  }

  const dataLine = body
    .split(/\r?\n/)
    .filter((line) => line.startsWith("data:"))
    .at(-1);
  if (!dataLine) throw new Error("The MCP server returned an empty response.");
  return JSON.parse(dataLine.slice(5).trim()) as JsonRpcPayload;
}

async function postRpc(
  endpoint: string,
  payload: Record<string, unknown>,
  sessionId?: string,
): Promise<{ response: Response; payload: JsonRpcPayload }> {
  const response = await fetch(endpoint, {
    method: "POST",
    cache: "no-store",
    headers: {
      Accept: ACCEPT_HEADER,
      "Content-Type": "application/json",
      ...(sessionId ? { "Mcp-Session-Id": sessionId } : {}),
    },
    body: JSON.stringify(payload),
    signal: AbortSignal.timeout(12_000),
  });
  if (!response.ok && response.status !== 202) {
    throw new Error(`MCP responded with HTTP ${response.status}.`);
  }
  if (response.status === 202) return { response, payload: {} };
  return { response, payload: await readRpcResponse(response) };
}

export async function callMcpTool<T>(
  name: McpToolName,
  args: Record<string, unknown>,
): Promise<T> {
  const endpoint = process.env.MCP_URL ?? "http://127.0.0.1:8000/mcp";
  let sessionId: string | null = null;

  try {
    const initialized = await postRpc(endpoint, {
      jsonrpc: "2.0",
      id: 1,
      method: "initialize",
      params: {
        protocolVersion: MCP_PROTOCOL_VERSION,
        capabilities: {},
        clientInfo: { name: "kitchen-dashboard", version: "1.0.0" },
      },
    });
    if (initialized.payload.error) {
      throw new Error(initialized.payload.error.message ?? "MCP initialize failed.");
    }
    sessionId = initialized.response.headers.get("mcp-session-id");

    await postRpc(
      endpoint,
      { jsonrpc: "2.0", method: "notifications/initialized" },
      sessionId ?? undefined,
    );
    const call = await postRpc(
      endpoint,
      {
        jsonrpc: "2.0",
        id: 2,
        method: "tools/call",
        params: { name, arguments: args },
      },
      sessionId ?? undefined,
    );
    if (call.payload.error) {
      throw new Error(call.payload.error.message ?? `The ${name} tool failed.`);
    }

    const result = call.payload.result;
    if (!result) throw new Error("The MCP server returned no result.");
    if (result.isError) {
      throw new Error(result.content?.map((block) => block.text).filter(Boolean).join("\n") || "The MCP tool failed.");
    }
    if (result.structuredContent !== undefined) {
      return result.structuredContent as T;
    }

    const text = result.content?.find((block) => block.text)?.text;
    if (text) return JSON.parse(text) as T;
    throw new Error("The MCP response contains no structured data.");
  } finally {
    if (sessionId) {
      await fetch(endpoint, {
        method: "DELETE",
        headers: { "Mcp-Session-Id": sessionId, Accept: ACCEPT_HEADER },
        signal: AbortSignal.timeout(2_000),
      }).catch(() => undefined);
    }
  }
}
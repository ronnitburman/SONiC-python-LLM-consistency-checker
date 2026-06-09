/**
 * SONiC MCP Bridge Extension
 *
 * Connects to the SONiC MCP server (streamable-http transport) and registers
 * all tools as pi custom tools.
 *
 * The Python MCP server runs on http://127.0.0.1:8100/mcp by default.
 * Start it with:  .venv/bin/python sonic_mcp_server.py
 *
 * For stdio mode (if preferred): .venv/bin/python sonic_mcp_server.py --transport stdio
 */
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StreamableHTTPClientTransport } from "@modelcontextprotocol/sdk/client/streamableHttp.js";

// ── config ─────────────────────────────────────────────────────────────

const MCP_SERVER_URL = new URL("http://127.0.0.1:8100/mcp");

// ── helpers ────────────────────────────────────────────────────────────

function jsonSchemaToTypeBox(schema: any): any {
  if (!schema || !schema.properties) {
    return Type.Object({});
  }

  const properties: Record<string, any> = {};
  const required: Set<string> = new Set(schema.required ?? []);

  for (const [name, prop] of Object.entries(schema.properties) as [string, any][]) {
    let field: any;

    switch (prop.type) {
      case "string":
        field = required.has(name) ? Type.String() : Type.Optional(Type.String());
        break;
      case "integer":
      case "number":
        field = required.has(name) ? Type.Number() : Type.Optional(Type.Number());
        break;
      case "boolean":
        field = required.has(name) ? Type.Boolean() : Type.Optional(Type.Boolean());
        break;
      default:
        field = Type.Optional(Type.String({ description: prop.description }));
    }

    if (prop.description) {
      field.description = prop.description;
    }

    properties[name] = field;
  }

  return Type.Object(properties);
}

// ── extension ──────────────────────────────────────────────────────────

export default async function (pi: ExtensionAPI) {
  let client: Client | null = null;
  let transport: StreamableHTTPClientTransport | null = null;

  pi.on("session_start", async (_event, ctx) => {
    try {
      transport = new StreamableHTTPClientTransport(MCP_SERVER_URL);

      client = new Client(
        { name: "sonic-mcp-client", version: "1.0.0" },
        { capabilities: {} },
      );

      await client.connect(transport);

      // Discover all tools from the MCP server
      const { tools } = await client.listTools();

      // Register each tool with pi
      for (const tool of tools) {
        pi.registerTool({
          name: tool.name,
          label: tool.name,
          description: tool.description ?? `SONiC tool: ${tool.name}`,
          parameters: jsonSchemaToTypeBox(tool.inputSchema),
          async execute(_toolCallId, params, _signal, onUpdate) {
            if (!client) {
              return {
                content: [{ type: "text", text: "MCP client not connected" }],
                isError: true,
              };
            }

            try {
              onUpdate?.({
                content: [{ type: "text", text: `Running ${tool.name}...` }],
              });

              const result = await client.callTool({
                name: tool.name,
                arguments: params as Record<string, unknown>,
              });

              const textContent = result.content
                .filter((c: any) => c.type === "text")
                .map((c: any) => c.text)
                .join("\n");

              return {
                content: [{ type: "text", text: textContent || JSON.stringify(result, null, 2) }],
                details: {},
              };
            } catch (err: any) {
              return {
                content: [{ type: "text", text: `Error: ${err.message}` }],
                isError: true,
              };
            }
          },
        });
      }

      ctx.ui?.notify?.(
        `SONiC MCP bridge connected via HTTP — ${tools.length} tools registered`,
        "info",
      );
    } catch (err: any) {
      ctx.ui?.notify?.(
        `SONiC MCP bridge failed: ${err.message}. Is the server running on ${MCP_SERVER_URL}?`,
        "warning",
      );
    }
  });

  // Cleanup on shutdown
  pi.on("session_shutdown", async () => {
    try {
      await client?.close();
    } catch {
      // ignore
    }
    transport = null;
    client = null;
  });
}

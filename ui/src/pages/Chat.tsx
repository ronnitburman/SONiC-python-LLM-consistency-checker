import { useState, useRef, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ChatMessage, ThinkingStep } from "../types";

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

function ThinkingBlock({ steps, streaming }: { steps: ThinkingStep[]; streaming: boolean }) {
  // Auto-expand while streaming, collapsed (user-toggleable) when done
  const [userOpen, setUserOpen] = useState(false);
  const open = streaming || userOpen;

  if (!steps || steps.length === 0) return null;

  return (
    <div style={{ marginBottom: "0.5rem", fontSize: "0.8rem" }}>
      <button
        onClick={() => !streaming && setUserOpen(!userOpen)}
        style={{
          background: "none",
          border: "none",
          cursor: streaming ? "default" : "pointer",
          color: "#6b7280",
          padding: "2px 0",
          fontFamily: "inherit",
          fontSize: "inherit",
        }}
      >
        {open ? "▾" : "▸"} Thinking ({steps.length} tool{steps.length > 1 ? "s" : ""})
        {streaming && " ..."}
      </button>
      {open && (
        <div
          style={{
            marginTop: "0.25rem",
            padding: "0.5rem",
            background: "#f9fafb",
            borderRadius: "0.5rem",
            border: "1px solid #e5e7eb",
            maxHeight: "200px",
            overflow: "auto",
          }}
        >
          {steps.map((step, i) => (
            <div key={i} style={{ marginBottom: i < steps.length - 1 ? "0.5rem" : 0 }}>
              <div style={{ fontWeight: 600, color: "#374151" }}>
                → {step.tool}
              </div>
              {step.result && (
                <div
                  style={{
                    color: "#6b7280",
                    fontSize: "0.75rem",
                    whiteSpace: "pre-wrap",
                    wordBreak: "break-word",
                    marginTop: "2px",
                  }}
                >
                  {step.result.length > 500
                    ? step.result.slice(0, 500) + `... (${step.result_full_len} chars total)`
                    : step.result}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function Chat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  async function send() {
    const text = input.trim();
    if (!text || loading) return;

    const userMsg: ChatMessage = {
      role: "user",
      content: text,
      object_type: "chat",
      object_name: "user",
    };

    // Placeholder for streaming response
    const agentMsg: ChatMessage = {
      role: "assistant",
      content: "",
      object_type: "chat",
      object_name: "agent",
      thinking_steps: [],
    };

    setMessages((m) => [...m, userMsg, agentMsg]);
    setInput("");
    setLoading(true);
    setError("");

    try {
      const response = await fetch(`${API_BASE_URL}/api/ai/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          messages: [
            ...messages.map((m) => ({ role: m.role, content: m.content })),
            { role: "user", content: text },
          ],
        }),
      });

      if (!response.ok) {
        const errText = await response.text();
        throw new Error(errText || `Request failed: ${response.status}`);
      }

      const reader = response.body?.getReader();
      if (!reader) throw new Error("No response body");

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        let eventType = "";
        for (const line of lines) {
          if (line.startsWith("event: ")) {
            eventType = line.slice(7).trim();
          } else if (line.startsWith("data: ")) {
            const data = JSON.parse(line.slice(6));
            if (eventType === "done") {
              setLoading(false);
            }
            handleSSEEvent(eventType, data);
          }
        }
      }
    } catch (e) {
      setError(String(e));
      // Remove the empty agent message on error
      setMessages((m) => m.filter((msg) => msg.content !== "" || msg.role !== "assistant"));
    } finally {
      setLoading(false);
    }
  }

  function handleSSEEvent(eventType: string, data: Record<string, unknown>) {
    setMessages((prev) => {
      const updated = [...prev];
      const lastIdx = updated.length - 1;
      if (lastIdx < 0 || updated[lastIdx].role !== "assistant") return prev;

      const agent = { ...updated[lastIdx] };
      const steps = agent.thinking_steps ? [...agent.thinking_steps] : [];

      if (eventType === "thinking") {
        const payload = data as { type: string; tool: string; result?: string; result_full_len?: number };
        if (payload.type === "tool_start") {
          // Clear any pre-tool text from the answer bubble (LLM may have
          // generated "Let me check..." before dispatching tool calls)
          if (steps.length === 0) {
            agent.content = "";
          }
          steps.push({ type: "tool_call", tool: payload.tool, args: {} });
        } else if (payload.type === "tool_end") {
          const last = steps[steps.length - 1];
          if (last) {
            last.result = payload.result;
            last.result_full_len = payload.result_full_len;
          }
        }
        agent.thinking_steps = steps;
      } else if (eventType === "token") {
        agent.content += (data.token as string) || "";
      }

      updated[lastIdx] = agent;
      return updated;
    });
  }

  async function resetChat() {
    setMessages([]);
    setError("");
    try {
      await fetch(`${API_BASE_URL}/api/ai/chat/reset`, { method: "POST" });
    } catch {}
  }

  return (
    <div>
      <div className="flex gap-2 items-center mb-1">
        <h2 style={{ margin: 0 }}>AI Chat</h2>
        <button className="secondary" onClick={resetChat}>
          Reset
        </button>
      </div>

      <p className="text-sm mb-1">
        Ask the agent to diagnose SONiC issues. It can inspect the switch,
        run consistency checks, and load technical skill documents.
      </p>

      <div
        style={{
          border: "1px solid #e5e7eb",
          borderRadius: "0.75rem",
          background: "white",
          height: "500px",
          overflow: "auto",
          padding: "1rem",
          marginBottom: "1rem",
        }}
      >
        {messages.length === 0 && !loading && (
          <div
            style={{
              textAlign: "center",
              color: "#9ca3af",
              paddingTop: "200px",
            }}
          >
            <p style={{ fontSize: "1.25rem", marginBottom: "0.5rem" }}>
              SONiC AI Diagnostic Agent
            </p>
            <p className="text-sm">
              Try: "Why is Ethernet0 down?" or "Run a full health check"
            </p>
          </div>
        )}

        {messages.map((msg, i) => (
          <div
            key={i}
            style={{
              marginBottom: "1rem",
              textAlign: msg.role === "user" ? "right" : "left",
            }}
          >
            {msg.role === "assistant" && msg.thinking_steps && (
              <div style={{ textAlign: "left", marginBottom: "0.25rem" }}>
                <div style={{ display: "inline-block", maxWidth: "80%" }}>
                  <ThinkingBlock steps={msg.thinking_steps} streaming={!msg.content} />
                </div>
              </div>
            )}
            {/* Only show the answer bubble once content starts arriving */}
            {(msg.role !== "assistant" || msg.content) && (
            <div
              style={{
                display: "inline-block",
                maxWidth: "80%",
                padding: "0.75rem 1rem",
                borderRadius: "0.75rem",
                background: msg.role === "user" ? "#111827" : "#f3f4f6",
                color: msg.role === "user" ? "white" : "#111827",
                textAlign: "left",
                fontSize: "0.9rem",
                lineHeight: "1.5",
              }}
            >
              {msg.role === "assistant" ? (
                <div className="markdown-body">
                  <ReactMarkdown remarkPlugins={[remarkGfm]}>{msg.content}</ReactMarkdown>
                </div>
              ) : (
                <div style={{ whiteSpace: "pre-wrap" }}>{msg.content}</div>
              )}
            </div>
            )}
          </div>
        ))}

        {loading && (
          <div style={{ textAlign: "left", marginBottom: "1rem" }}>
            <div
              style={{
                display: "inline-block",
                padding: "0.75rem 1rem",
                borderRadius: "0.75rem",
                background: "#f3f4f6",
              }}
            >
              <span className="spinner" />
            </div>
          </div>
        )}

        {error && (
          <div className="error" style={{ margin: "0.5rem 0" }}>
            {error}
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      <div style={{ display: "flex", gap: "0.5rem" }}>
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send()}
          placeholder="Ask about a port, run a health check, diagnose an issue..."
          style={{ flex: 1, marginBottom: 0 }}
          disabled={loading}
        />
        <button onClick={send} disabled={loading || !input.trim()}>
          Send
        </button>
      </div>
    </div>
  );
}

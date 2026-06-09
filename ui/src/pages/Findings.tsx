import { useState } from "react";
import { Card } from "../components/Card";
import { FindingCard } from "../components/FindingCard";
import { getFindings } from "../api";
import type { Finding } from "../types";

export function Findings() {
  const [findings, setFindings] = useState<Finding[]>([]);
  const [extended, setExtended] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [loaded, setLoaded] = useState(false);

  async function handleLoad() {
    setError("");
    setLoading(true);
    try {
      const result = await getFindings(extended);
      setFindings(result.findings);
      setLoaded(true);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  const grouped: Record<string, Finding[]> = {};
  for (const f of findings) {
    const key = f.severity;
    if (!grouped[key]) grouped[key] = [];
    grouped[key].push(f);
  }

  const order = ["critical", "warning", "info"];

  return (
    <div>
      <Card title="Findings">
        <div className="toolbar">
          <label className="flex gap-2 items-center text-sm">
            <input
              type="checkbox"
              checked={extended}
              onChange={(e) => {
                setExtended(e.target.checked);
                setLoaded(false);
              }}
            />
            Extended checks (routes, VLANs, LAGs)
          </label>
          <button onClick={handleLoad} disabled={loading}>
            {loading ? "Loading..." : "Refresh"}
          </button>
        </div>

        {error && <div className="error">{error}</div>}

        {loading && (
          <div className="loading">
            <span className="spinner" /> Running checks...
          </div>
        )}

        {loaded && findings.length === 0 && (
          <div className="empty">No findings found.</div>
        )}

        {loaded &&
          order.map((severity) => {
            const group = grouped[severity];
            if (!group || group.length === 0) return null;
            return (
              <div key={severity} className="mb-1">
                <h3
                  style={{
                    color:
                      severity === "critical"
                        ? "#ef4444"
                        : severity === "warning"
                          ? "#f59e0b"
                          : "#3b82f6",
                    textTransform: "uppercase",
                    fontSize: "0.85rem",
                  }}
                >
                  {severity} ({group.length})
                </h3>
                {group.map((f) => (
                  <FindingCard key={f.id} finding={f} />
                ))}
              </div>
            );
          })}
      </Card>
    </div>
  );
}

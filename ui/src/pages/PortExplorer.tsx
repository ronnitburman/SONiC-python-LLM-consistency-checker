import { useState } from "react";
import { Card } from "../components/Card";
import { JsonViewer } from "../components/JsonViewer";
import { KeyValueTable } from "../components/KeyValueTable";
import { FindingCard } from "../components/FindingCard";
import { StatusBadge } from "../components/StatusBadge";
import { getPort, getPortSummary } from "../api";
import type { PortView, DiagnosticSummary } from "../types";
import type { AppData } from "../App";

type Props = { data: AppData };

export function PortExplorer({ data }: Props) {
  const portList = data.ports?.ports ?? [];
  const [selectedPort, setSelectedPort] = useState<string>("");
  const [portView, setPortView] = useState<PortView | null>(null);
  const [portSummary, setPortSummary] = useState<DiagnosticSummary | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSelect(portName: string) {
    setSelectedPort(portName);
    setError("");
    setLoading(true);
    setPortView(null);
    setPortSummary(null);
    try {
      const [pv, ps] = await Promise.all([
        getPort(portName),
        getPortSummary(portName).catch(() => null),
      ]);
      setPortView(pv);
      setPortSummary(ps);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <Card title="Port Explorer">
        {error && <div className="error">{error}</div>}

        <p className="text-sm">Click a port to load its cross-DB view.</p>

        {portList.length === 0 ? (
          <div className="empty">No ports discovered.</div>
        ) : (
          <div className="key-list">
            {portList.map((p) => (
              <div
                key={p}
                className={`key-list-item ${selectedPort === p ? "selected" : ""}`}
                onClick={() => handleSelect(p)}
              >
                {p}
              </div>
            ))}
          </div>
        )}

        {loading && (
          <div className="loading mt-1">
            <span className="spinner" /> Loading {selectedPort}...
          </div>
        )}

        {portView && (
          <>
            {/* ── Port Summary (Step 4A) ──────────────────────── */}
            {portSummary && (
              <div className="flex gap-2 items-center mt-1 mb-1">
                <StatusBadge
                  label={`${portSummary.overall_health_score}/100`}
                  tone={portSummary.overall_status === "healthy" ? "ok" : portSummary.overall_status === "warning" ? "warning" : "critical"}
                />
                <span className="text-sm">
                  {portSummary.total_findings} findings
                  {portSummary.critical_count > 0 && <span style={{ color: "#ef4444" }}> ({portSummary.critical_count}c)</span>}
                  {portSummary.warning_count > 0 && <span style={{ color: "#f59e0b" }}> ({portSummary.warning_count}w)</span>}
                </span>
              </div>
            )}

            {/* ── DB Sections ─────────────────────────────────── */}
            <div className="port-sections">
              <Card title="CONFIG_DB">
                <span className="text-sm mono">{portView.raw_keys.CONFIG_DB?.join(", ") || "N/A"}</span>
                <KeyValueTable data={portView.config} />
              </Card>

              <Card title="APPL_DB">
                <span className="text-sm mono">{portView.raw_keys.APPL_DB?.join(", ") || "N/A"}</span>
                <KeyValueTable data={portView.app} />
              </Card>

              <Card title="STATE_DB">
                <span className="text-sm mono">{portView.raw_keys.STATE_DB?.join(", ") || "N/A"}</span>
                <KeyValueTable data={portView.state} />
              </Card>

              <Card title="Transceiver"><JsonViewer data={portView.transceiver} /></Card>
              <Card title="Counters"><JsonViewer data={portView.counters} /></Card>
              <Card title="ASIC_DB"><JsonViewer data={portView.asic} /></Card>
            </div>

            <Card title="Raw Keys"><JsonViewer data={portView.raw_keys} /></Card>

            <Card title={`Findings (${portView.findings.length})`}>
              {portView.findings.length === 0 ? (
                <div className="empty">No findings for this port.</div>
              ) : (
                portView.findings.map((f) => <FindingCard key={f.id} finding={f} />)
              )}
            </Card>
          </>
        )}
      </Card>
    </div>
  );
}

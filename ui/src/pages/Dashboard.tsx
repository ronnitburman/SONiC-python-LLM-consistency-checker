import { useState } from "react";
import { Card } from "../components/Card";
import { StatusBadge } from "../components/StatusBadge";
import { getSummary } from "../api";
import type { DiagnosticSummary } from "../types";
import type { AppData } from "../App";

type Props = { data: AppData };

export function Dashboard({ data }: Props) {
  const [summary, setSummary] = useState<DiagnosticSummary | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [summaryError, setSummaryError] = useState("");

  async function loadSummary() {
    setSummaryLoading(true);
    setSummaryError("");
    try {
      const s = await getSummary(true);
      setSummary(s);
    } catch (e) {
      setSummaryError(String(e));
    } finally {
      setSummaryLoading(false);
    }
  }

  const { health, dbConfig, dbs, ports, swss, error, loaded } = data;

  if (!loaded) {
    return <div className="loading"><span className="spinner" /> Connecting to backend...</div>;
  }

  return (
    <div>
      {error && <div className="error">{error}</div>}

      {/* ── Onboarding guide (shown until summary is loaded) ── */}
      {!summary && !summaryLoading && (
        <div className="guide-box">
          <h3>Welcome to the SONiC Consistency Checker</h3>
          <p>
            This tool inspects your SONiC switch across all Redis databases
            and detects inconsistencies between configuration, runtime state,
            and ASIC programming.
          </p>
          <p><strong>Quick start:</strong></p>
          <ol>
            <li>
              Click <strong>"Load Summary"</strong> below to run a full health check
              (port checks, route drift, VLAN membership, LAG health)
            </li>
            <li>
              Switch to <strong>DB Explorer</strong> to browse raw Redis keys
              and see equivalent <code>redis-cli</code> commands
            </li>
            <li>
              Switch to <strong>Port Explorer</strong> to inspect a port across
              all DBs (CONFIG_DB, APPL_DB, STATE_DB, ASIC_DB, counters, transceivers)
            </li>
            <li>
              Switch to <strong>Findings</strong> to see all detected
              inconsistencies with evidence and suggested remediation commands
            </li>
            <li>
              Switch to <strong>SWSS SDK</strong> to compare raw Redis reads
              with SONiC-native SDK reads (ConfigDBConnector, SonicV2Connector)
            </li>
          </ol>
        </div>
      )}

      {/* ── Top-line status cards ─────────────────────────────── */}
      <div className="grid">
        <Card title="Backend">
          <StatusBadge
            label={health === "ok" ? "OK" : health === "loading" ? "..." : "ERROR"}
            tone={health === "ok" ? "ok" : "error"}
          />
        </Card>

        <Card title="DB Config">
          {dbConfig && (
            <>
              <div className="text-sm mt-1">
                Source: <span className="mono">{dbConfig.source}</span>
              </div>
              <div className="text-sm mt-1">
                Fallback:{" "}
                <StatusBadge
                  label={dbConfig.used_fallback ? "YES — WARNING" : "No"}
                  tone={dbConfig.used_fallback ? "warning" : "ok"}
                />
              </div>
            </>
          )}
        </Card>

        <Card title="Ports">
          {ports && <strong>{ports.ports.length}</strong>}
          {" "}discovered
        </Card>

        <Card title="SWSS SDK">
          {swss && (
            <StatusBadge
              label={swss.available ? "Available" : "Unavailable"}
              tone={swss.available ? "ok" : "warning"}
            />
          )}
        </Card>
      </div>

      {/* ── DB Sizes Table ────────────────────────────────────── */}
      {dbs.length > 0 && (
        <Card title="DB Sizes">
          <table>
            <thead>
              <tr><th>DB Name</th><th>ID</th><th>Keys</th></tr>
            </thead>
            <tbody>
              {dbs.map((db) => (
                <tr key={db.db_name}>
                  <td className="mono">{db.db_name}</td>
                  <td>{db.db_id}</td>
                  <td>{db.error ? <StatusBadge label={db.error} tone="error" /> : db.size}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}

      {/* ── Health Summary (lazy — explicit load) ────────────── */}
      <Card title="Health Summary">
        {!summary && !summaryLoading && (
          <div>
            <p className="text-sm">
              Runs route drift, VLAN membership, and LAG member checks.
              This may take a few seconds.
            </p>
            <button onClick={loadSummary}>Load Summary</button>
          </div>
        )}

        {summaryLoading && (
          <div className="loading"><span className="spinner" /> Running checks...</div>
        )}

        {summaryError && <div className="error">{summaryError}</div>}

        {summary && (
          <div>
            {/* Health score */}
            <div className="health-score">
              <StatusBadge
                label={summary.overall_status.toUpperCase()}
                tone={summary.overall_status === "healthy" ? "ok" : summary.overall_status === "warning" ? "warning" : "critical"}
              />
            </div>
            <div className="health-bar mt-1">
              <div className={`health-bar-fill ${summary.overall_status}`} style={{ width: `${summary.overall_health_score}%` }} />
            </div>
            <div className="text-sm mt-1">
              {summary.total_findings} findings:{" "}
              <span style={{ color: "#ef4444" }}>{summary.critical_count}c</span>{" "}
              <span style={{ color: "#f59e0b" }}>{summary.warning_count}w</span>{" "}
              <span style={{ color: "#3b82f6" }}>{summary.info_count}i</span>
            </div>

            {/* Subsystem cards */}
            <div className="summary-grid mt-1">
              {summary.route_drift && (
                <Card title="Route Table Drift">
                  <StatusBadge label={summary.route_drift.status.toUpperCase()} tone={summary.route_drift.status === "ok" ? "ok" : summary.route_drift.status === "drift" ? "critical" : "warning"} />
                  <div className="text-sm mt-1">APPL_DB: <strong>{summary.route_drift.appl_route_count}</strong></div>
                  <div className="text-sm">ASIC_DB: <strong>{summary.route_drift.asic_route_count}</strong></div>
                  {summary.route_drift.drift > 0 && <div className="text-sm" style={{ color: "#ef4444" }}>Drift: <strong>{summary.route_drift.drift}</strong></div>}
                </Card>
              )}
              {summary.vlan_membership && (
                <Card title="VLAN Membership">
                  <StatusBadge label={summary.vlan_membership.status.toUpperCase()} tone={summary.vlan_membership.status === "ok" ? "ok" : "warning"} />
                </Card>
              )}
              {summary.lag_member_health && (
                <Card title="LAG Member Health">
                  <StatusBadge label={summary.lag_member_health.status.toUpperCase()} tone={summary.lag_member_health.status === "ok" ? "ok" : "warning"} />
                </Card>
              )}
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}

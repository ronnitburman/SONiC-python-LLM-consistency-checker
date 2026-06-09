import type { Finding } from "../types";
import { JsonViewer } from "./JsonViewer";
import { StatusBadge } from "./StatusBadge";

type FindingCardProps = {
  finding: Finding;
};

export function FindingCard({ finding }: FindingCardProps) {
  const severityClass = `severity-${finding.severity}`;

  return (
    <div className={`finding-card ${severityClass}`}>
      <div className="finding-header">
        <StatusBadge
          label={finding.severity.toUpperCase()}
          tone={
            finding.severity === "critical"
              ? "critical"
              : finding.severity === "warning"
                ? "warning"
                : "info"
          }
        />
        <span className="text-sm mono">
          {finding.category}
          {finding.object_name !== "system" && ` — ${finding.object_name}`}
        </span>
      </div>

      <div className="finding-summary">{finding.summary}</div>

      <div className="finding-detail">
        {Object.keys(finding.evidence).length > 0 && (
          <>
            <h4>Evidence</h4>
            <JsonViewer data={finding.evidence} />
          </>
        )}

        {finding.possible_causes.length > 0 && (
          <>
            <h4>Possible Causes</h4>
            <ul>
              {finding.possible_causes.map((c, i) => (
                <li key={i}>{c}</li>
              ))}
            </ul>
          </>
        )}

        {finding.suggested_commands.length > 0 && (
          <>
            <h4>Suggested Commands</h4>
            <ul>
              {finding.suggested_commands.map((cmd, i) => (
                <li key={i}>
                  <code>{cmd}</code>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
    </div>
  );
}

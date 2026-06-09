type StatusBadgeProps = {
  label: string;
  tone?: "ok" | "warning" | "error" | "neutral" | "info" | "critical";
};

export function StatusBadge({ label, tone = "neutral" }: StatusBadgeProps) {
  return <span className={`badge badge-${tone}`}>{label}</span>;
}

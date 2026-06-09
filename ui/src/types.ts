// ── Step 1: DB Config ───────────────────────────────────────────────

export type DbEntry = {
  id: number;
  separator: string;
  instance: string;
};

export type DbConfigResponse = {
  source: string;
  used_fallback: boolean;
  databases: Record<string, DbEntry>;
  errors: string[];
};

// ── Step 2: DB Explorer ─────────────────────────────────────────────

export type DbSizeSummary = {
  db_name: string;
  db_id: number;
  size: number;
  error?: string | null;
};

export type DbKeysResponse = {
  db_name: string;
  db_id: number;
  pattern: string;
  keys: string[];
  equivalent_redis: string;
};

export type SonicDbKey = {
  db_name: string;
  db_id: number;
  key: string;
  key_type?: string | null;
  fields: Record<string, unknown>;
  equivalent_redis?: string | null;
};

export type KeyTypeResponse = {
  db_name: string;
  key: string;
  key_type: string;
};

// ── Step 3: Port View ───────────────────────────────────────────────

export type PortView = {
  name: string;
  config: Record<string, unknown>;
  app: Record<string, unknown>;
  state: Record<string, unknown>;
  asic: Record<string, unknown>;
  counters: Record<string, unknown>;
  transceiver: Record<string, unknown>;
  raw_keys: Record<string, string[]>;
  findings: Finding[];
};

export type PortsListResponse = {
  ports: string[];
  source: string;
};

// ── Step 4: Consistency Checks ──────────────────────────────────────

export type Finding = {
  id: string;
  severity: "info" | "warning" | "critical";
  category: string;
  object_type: string;
  object_name: string;
  summary: string;
  evidence: Record<string, unknown>;
  possible_causes: string[];
  suggested_commands: string[];
};

export type FindingsResponse = {
  findings: Finding[];
};

// ── Step 4A: Summary & Extended Checks ──────────────────────────────

export type RouteDriftSummary = {
  appl_route_count: number;
  asic_route_count: number;
  drift: number;
  status: "ok" | "drift" | "unknown";
};

export type VlanMembershipSummary = {
  config_vlan_count: number;
  app_vlan_count: number;
  vlans_with_mismatch: string[];
  status: "ok" | "mismatch" | "unknown";
};

export type LagMemberSummary = {
  config_lag_count: number;
  app_lag_count: number;
  lags_with_mismatch: string[];
  status: "ok" | "mismatch" | "unknown";
};

export type DiagnosticSummary = {
  total_findings: number;
  critical_count: number;
  warning_count: number;
  info_count: number;
  categories: Record<string, number>;
  port_checks: Record<string, number>;
  route_drift: RouteDriftSummary | null;
  vlan_membership: VlanMembershipSummary | null;
  lag_member_health: LagMemberSummary | null;
  overall_health_score: number;
  overall_status: "healthy" | "warning" | "critical";
};

// ── Step 5: SWSS SDK ────────────────────────────────────────────────

export type SwssCheckResponse = {
  available: boolean;
  swsssdk_available: boolean;
  swsscommon_available: boolean;
  message: string;
  errors: string[];
};

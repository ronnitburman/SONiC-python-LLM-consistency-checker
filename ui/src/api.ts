import type {
  DbConfigResponse,
  DbKeysResponse,
  DbSizeSummary,
  DiagnosticSummary,
  FindingsResponse,
  KeyTypeResponse,
  PortView,
  PortsListResponse,
  SonicDbKey,
  SwssCheckResponse,
} from "./types";

const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`);

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }

  return response.json() as Promise<T>;
}

// ── Health ───────────────────────────────────────────────────────────

export function getHealth() {
  return getJson<{ status: string }>("/health");
}

// ── Step 1: DB Config ────────────────────────────────────────────────

export function getDbConfig() {
  return getJson<DbConfigResponse>("/api/db-config");
}

// ── Step 2: DB Explorer ──────────────────────────────────────────────

export function getDbs() {
  return getJson<DbSizeSummary[]>("/api/dbs");
}

export function getDbKeys(dbName: string, pattern: string) {
  return getJson<DbKeysResponse>(
    `/api/dbs/${encodeURIComponent(dbName)}/keys?pattern=${encodeURIComponent(pattern)}`
  );
}

export function getDbKey(dbName: string, key: string) {
  return getJson<SonicDbKey>(
    `/api/dbs/${encodeURIComponent(dbName)}/key?key=${encodeURIComponent(key)}`
  );
}

export function getDbKeyType(dbName: string, key: string) {
  return getJson<KeyTypeResponse>(
    `/api/dbs/${encodeURIComponent(dbName)}/type?key=${encodeURIComponent(key)}`
  );
}

// ── Step 3: Ports ────────────────────────────────────────────────────

export function getPorts() {
  return getJson<PortsListResponse>("/api/ports");
}

export function getPort(portName: string) {
  return getJson<PortView>(`/api/ports/${encodeURIComponent(portName)}`);
}

// ── Step 4: Findings ─────────────────────────────────────────────────

export function getFindings(extended = false) {
  const qs = extended ? "?extended=true" : "";
  return getJson<FindingsResponse>(`/api/findings${qs}`);
}

export function getPortFindings(portName: string) {
  return getJson<FindingsResponse>(
    `/api/ports/${encodeURIComponent(portName)}/findings`
  );
}

// ── Step 4A: Summary ─────────────────────────────────────────────────

export function getSummary(extended = true) {
  const qs = extended ? "" : "?extended=false";
  return getJson<DiagnosticSummary>(`/api/summary${qs}`);
}

export function getPortSummary(portName: string) {
  return getJson<DiagnosticSummary>(
    `/api/ports/${encodeURIComponent(portName)}/summary`
  );
}

// ── Step 5: SWSS SDK ─────────────────────────────────────────────────

export function getSwssCheck() {
  return getJson<SwssCheckResponse>("/api/swss/check");
}

export function getSwssConfigTable(table: string) {
  return getJson<Record<string, unknown>>(
    `/api/swss/config/${encodeURIComponent(table)}`
  );
}

export function getSwssConfigEntry(table: string, key: string) {
  return getJson<Record<string, unknown>>(
    `/api/swss/config/${encodeURIComponent(table)}/${encodeURIComponent(key)}`
  );
}

export function getSwssV2Keys(dbName: string, pattern: string) {
  return getJson<Record<string, unknown>>(
    `/api/swss/v2/${encodeURIComponent(dbName)}/keys?pattern=${encodeURIComponent(pattern)}`
  );
}

export function getSwssV2Key(dbName: string, key: string) {
  return getJson<Record<string, unknown>>(
    `/api/swss/v2/${encodeURIComponent(dbName)}/key?key=${encodeURIComponent(key)}`
  );
}

export function getSwssTable(dbName: string, table: string) {
  return getJson<Record<string, unknown>>(
    `/api/swss/table/${encodeURIComponent(dbName)}/${encodeURIComponent(table)}`
  );
}

export function getSwssTableEntry(
  dbName: string,
  table: string,
  key: string
) {
  return getJson<Record<string, unknown>>(
    `/api/swss/table/${encodeURIComponent(dbName)}/${encodeURIComponent(table)}/${encodeURIComponent(key)}`
  );
}

export function getSwssCompareConfig(table: string, key: string) {
  return getJson<Record<string, unknown>>(
    `/api/swss/compare/config/${encodeURIComponent(table)}/${encodeURIComponent(key)}`
  );
}

import { Card } from "../components/Card";
import { JsonViewer } from "../components/JsonViewer";
import { StatusBadge } from "../components/StatusBadge";
import {
  getSwssConfigTable,
  getSwssConfigEntry,
  getSwssV2Keys,
  getSwssV2Key,
  getSwssTable,
  getSwssTableEntry,
  getSwssCompareConfig,
} from "../api";
import type { AppData } from "../App";
import { useState } from "react";

type Props = { data: AppData };

export function SwssSdkExplorer({ data }: Props) {
  const swss = data.swss;

  return (
    <div>
      {/* ── SWSS Status ───────────────────────────────────────── */}
      <Card title="SWSS SDK Status">
        {swss ? (
          <div>
            <div className="flex gap-2 items-center">
              <StatusBadge
                label={swss.available ? "Available" : "Unavailable"}
                tone={swss.available ? "ok" : "warning"}
              />
            </div>
            <div className="text-sm mt-1">
              swsssdk:{" "}
              <StatusBadge label={swss.swsssdk_available ? "OK" : "Missing"} tone={swss.swsssdk_available ? "ok" : "warning"} />
              {" "}swsscommon:{" "}
              <StatusBadge label={swss.swsscommon_available ? "OK" : "Missing"} tone={swss.swsscommon_available ? "ok" : "warning"} />
            </div>
            <div className="text-sm mt-1">{swss.message}</div>
            {swss.errors.map((e, i) => (
              <div key={i} className="text-sm" style={{ color: "#d97706" }}>{e}</div>
            ))}
          </div>
        ) : (
          <div className="loading"><span className="spinner" /></div>
        )}
      </Card>

      <SwssSection title="ConfigDBConnector" fields={[
        { name: "table", label: "Table", default: "PORT" },
        { name: "key", label: "Key", default: "Ethernet0" },
      ]} actions={[
        { label: "Get Table", handler: async (v) => getSwssConfigTable(v.table) },
        { label: "Get Entry", handler: async (v) => getSwssConfigEntry(v.table, v.key) },
      ]} />

      <SwssSection title="SonicV2Connector" fields={[
        { name: "dbName", label: "DB", default: "CONFIG_DB" },
        { name: "pattern", label: "Pattern", default: "PORT*" },
        { name: "key", label: "Key", default: "PORT|Ethernet0" },
      ]} actions={[
        { label: "V2 Keys", handler: async (v) => getSwssV2Keys(v.dbName, v.pattern) },
        { label: "V2 HGETALL", handler: async (v) => getSwssV2Key(v.dbName, v.key) },
      ]} />

      <SwssSection title="Table Reader (Raw Redis)" fields={[
        { name: "dbName", label: "DB", default: "CONFIG_DB" },
        { name: "table", label: "Table", default: "PORT" },
        { name: "key", label: "Key", default: "Ethernet0" },
      ]} actions={[
        { label: "Get Table Keys", handler: async (v) => getSwssTable(v.dbName, v.table) },
        { label: "Get Table Entry", handler: async (v) => getSwssTableEntry(v.dbName, v.table, v.key) },
      ]} />

      <SwssSection title="Compare: Raw Redis vs SWSS SDK" fields={[
        { name: "table", label: "Table", default: "PORT" },
        { name: "key", label: "Key", default: "Ethernet0" },
      ]} actions={[
        { label: "Compare", handler: async (v) => getSwssCompareConfig(v.table, v.key) },
      ]} />
    </div>
  );
}

/* ── Reusable SWSS section ────────────────────────────────────────── */

type FieldDef = { name: string; label: string; default: string };
type ActionDef = { label: string; handler: (v: Record<string, string>) => Promise<Record<string, unknown>> };

function SwssSection({ title, fields, actions }: { title: string; fields: FieldDef[]; actions: ActionDef[] }) {
  const [values, setValues] = useState<Record<string, string>>(() => {
    const init: Record<string, string> = {};
    fields.forEach((f) => (init[f.name] = f.default));
    return init;
  });
  const [result, setResult] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function runAction(handler: ActionDef["handler"]) {
    setError("");
    setLoading(true);
    try {
      const r = await handler(values);
      setResult(r);
    } catch (e) {
      setError(String(e));
      setResult(null);
    } finally {
      setLoading(false);
    }
  }

  return (
    <Card title={title}>
      <div className="toolbar">
        {fields.map((f) => (
          <input key={f.name} type="text" placeholder={f.label} value={values[f.name] || ""}
            onChange={(e) => setValues((v) => ({ ...v, [f.name]: e.target.value }))} />
        ))}
        {actions.map((a) => (
          <button key={a.label} onClick={() => runAction(a.handler)} disabled={loading}>{a.label}</button>
        ))}
      </div>
      {loading && <div className="loading"><span className="spinner" /></div>}
      {error && <div className="error">{error}</div>}
      {result && (
        <>
          {result.method && <div className="text-sm mono mb-1">Method: {String(result.method)}</div>}
          {result.equivalent_redis && <div className="text-sm mono mb-1">{String(result.equivalent_redis)}</div>}
          <JsonViewer data={result} />
        </>
      )}
    </Card>
  );
}

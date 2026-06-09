import { useState } from "react";
import { Card } from "../components/Card";
import { JsonViewer } from "../components/JsonViewer";
import { getDbKeys, getDbKey } from "../api";
import type { DbKeysResponse, SonicDbKey } from "../types";
import type { AppData } from "../App";

type Props = { data: AppData };

export function DbExplorer({ data }: Props) {
  const databases = data.dbConfig?.databases ?? {};
  const [dbName, setDbName] = useState("CONFIG_DB");
  const [pattern, setPattern] = useState("PORT*");
  const [keysResult, setKeysResult] = useState<DbKeysResponse | null>(null);
  const [selectedKey, setSelectedKey] = useState<string | null>(null);
  const [keyResult, setKeyResult] = useState<SonicDbKey | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleScan() {
    setError("");
    setLoading(true);
    setKeysResult(null);
    setSelectedKey(null);
    setKeyResult(null);
    try {
      const result = await getDbKeys(dbName, pattern);
      setKeysResult(result);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  async function handleKeyClick(key: string) {
    setSelectedKey(key);
    setError("");
    try {
      const result = await getDbKey(dbName, key);
      setKeyResult(result);
    } catch (e) {
      setError(String(e));
    }
  }

  return (
    <div>
      <Card title="DB Explorer">
        <div className="toolbar">
          <select value={dbName} onChange={(e) => setDbName(e.target.value)}>
            {Object.keys(databases).sort().map((name) => (
              <option key={name} value={name}>{name}</option>
            ))}
          </select>

          <input
            type="text"
            value={pattern}
            onChange={(e) => setPattern(e.target.value)}
            placeholder="Pattern (e.g. PORT*)"
            onKeyDown={(e) => e.key === "Enter" && handleScan()}
          />

          <button onClick={handleScan} disabled={loading}>
            {loading ? "Scanning..." : "Scan"}
          </button>
        </div>

        {error && <div className="error">{error}</div>}

        {keysResult && (
          <div className="text-sm mb-1">
            <span className="mono">{keysResult.equivalent_redis}</span>
          </div>
        )}

        {loading && <div className="loading"><span className="spinner" /> Scanning...</div>}

        {keysResult && (
          <div className="grid-2">
            <div>
              <strong>Keys ({keysResult.keys.length})</strong>
              {keysResult.keys.length === 0 ? (
                <div className="empty">No keys found.</div>
              ) : (
                <div className="key-list">
                  {keysResult.keys.map((key) => (
                    <div
                      key={key}
                      className={`key-list-item ${selectedKey === key ? "selected" : ""}`}
                      onClick={() => handleKeyClick(key)}
                    >
                      {key}
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div>
              {selectedKey && (
                <>
                  <strong>Key Details</strong>
                  {keyResult ? (
                    <div>
                      <div className="text-sm mt-1">Type: <strong>{keyResult.key_type || "unknown"}</strong></div>
                      {keyResult.equivalent_redis && (
                        <div className="text-sm mono mt-1">{keyResult.equivalent_redis}</div>
                      )}
                      <div className="mt-1"><JsonViewer data={keyResult.fields} /></div>
                    </div>
                  ) : (
                    <div className="loading"><span className="spinner" /></div>
                  )}
                </>
              )}
            </div>
          </div>
        )}
      </Card>
    </div>
  );
}

import { useEffect, useState } from "react";
import { Dashboard } from "./pages/Dashboard";
import { DbExplorer } from "./pages/DbExplorer";
import { PortExplorer } from "./pages/PortExplorer";
import { Findings } from "./pages/Findings";
import { SwssSdkExplorer } from "./pages/SwssSdkExplorer";
import { getHealth, getDbConfig, getDbs, getPorts, getSwssCheck } from "./api";
import type { DbConfigResponse, DbSizeSummary, PortsListResponse, SwssCheckResponse } from "./types";

/* ── Shared data context (fetched once, used by all pages) ──────── */

export type AppData = {
  health: string;
  dbConfig: DbConfigResponse | null;
  dbs: DbSizeSummary[];
  ports: PortsListResponse | null;
  swss: SwssCheckResponse | null;
  error: string;
  loaded: boolean;
};

type Page = "dashboard" | "db" | "ports" | "findings" | "swss";

const PAGES: { key: Page; label: string }[] = [
  { key: "dashboard", label: "Dashboard" },
  { key: "db", label: "DB Explorer" },
  { key: "ports", label: "Port Explorer" },
  { key: "findings", label: "Findings" },
  { key: "swss", label: "SWSS SDK" },
];

export default function App() {
  const [page, setPage] = useState<Page>("dashboard");
  const [data, setData] = useState<AppData>({
    health: "loading",
    dbConfig: null,
    dbs: [],
    ports: null,
    swss: null,
    error: "",
    loaded: false,
  });

  /* Fetch lightweight shared data ONCE at mount */
  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const h = await getHealth();
        if (cancelled) return;
        const [cfg, dbList, p, swssResult] = await Promise.all([
          getDbConfig(),
          getDbs(),
          getPorts(),
          getSwssCheck(),
        ]);
        if (cancelled) return;
        setData({
          health: h.status,
          dbConfig: cfg,
          dbs: dbList,
          ports: p,
          swss: swssResult,
          error: "",
          loaded: true,
        });
      } catch (e) {
        if (!cancelled) {
          setData((d) => ({
            ...d,
            health: "error",
            error: `Connection failed: ${e}`,
            loaded: true,
          }));
        }
      }
    }
    load();
    return () => { cancelled = true; };
  }, []);

  return (
    <div className="app-shell">
      <header className="header">
        <h1>SONiC Consistency Checker</h1>
      </header>

      <nav className="nav">
        {PAGES.map((p) => (
          <button
            key={p.key}
            className={page === p.key ? "active" : ""}
            onClick={() => setPage(p.key)}
          >
            {p.label}
          </button>
        ))}
      </nav>

      <main className="page">
        {/* Keep all pages mounted so state survives tab switches */}
        <div style={{ display: page === "dashboard" ? "block" : "none" }}>
          <Dashboard data={data} />
        </div>
        <div style={{ display: page === "db" ? "block" : "none" }}>
          <DbExplorer data={data} />
        </div>
        <div style={{ display: page === "ports" ? "block" : "none" }}>
          <PortExplorer data={data} />
        </div>
        <div style={{ display: page === "findings" ? "block" : "none" }}>
          <Findings />
        </div>
        <div style={{ display: page === "swss" ? "block" : "none" }}>
          <SwssSdkExplorer data={data} />
        </div>
      </main>
    </div>
  );
}

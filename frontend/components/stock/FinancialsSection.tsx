"use client";

// FinancialsSection — tabbed financial tables (Quarterly, Annual, BS, CF, Shareholding)

import { useEffect, useState } from "react";
import { fetchFinancials } from "@/lib/api";
import type { Financials, FinancialTable } from "@/lib/types";
import { Skeleton } from "@/components/ui/Skeleton";
import SectionHeader from "@/components/ui/SectionHeader";
import Tabs from "@/components/ui/Tabs";

interface FinancialsSectionProps {
  symbol: string;
}

const TABS = [
  { id: "quarterly", label: "Quarterly" },
  { id: "annual", label: "Annual" },
  { id: "balance_sheet", label: "Balance Sheet" },
  { id: "cash_flow", label: "Cash Flow" },
  { id: "shareholding", label: "Shareholding" },
  { id: "mf_holdings", label: "MF Holdings" },
];

interface MFRow {
  name: string;
  current: number | null;
  onePeriodChange: number | null;
  threePeriodChange: number | null;
  trend: number[];
}

function toNum(v: number | string | null | undefined): number | null {
  if (typeof v === "number" && Number.isFinite(v)) return v;
  if (typeof v === "string") {
    const n = Number(v.replace(/,/g, "").trim());
    return Number.isFinite(n) ? n : null;
  }
  return null;
}

function fmtPct(v: number | null): string {
  if (v == null) return "—";
  const sign = v > 0 ? "+" : "";
  return `${sign}${v.toFixed(2)}%`;
}

function Sparkline({ values }: { values: number[] }) {
  if (values.length < 2) {
    return <span className="text-xs text-zinc-500">—</span>;
  }

  const width = 96;
  const height = 24;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const points = values
    .map((v, i) => {
      const x = (i / (values.length - 1)) * width;
      const y = height - ((v - min) / range) * height;
      return `${x},${y}`;
    })
    .join(" ");

  const delta = values[values.length - 1] - values[0];
  const stroke = delta >= 0 ? "#65a30d" : "#ef4444";

  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`}>
      <polyline points={points} fill="none" stroke={stroke} strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}

function deriveMFRows(table: FinancialTable): MFRow[] {
  const rows = table.rows ?? [];

  return rows
    .map((row) => {
      const parsed = (row.values ?? []).map(toNum);
      const currentIndex = parsed.findIndex((v) => v != null);
      if (currentIndex < 0) {
        return {
          name: row.label,
          current: null,
          onePeriodChange: null,
          threePeriodChange: null,
          trend: [],
        };
      }

      const current = parsed[currentIndex];
      const previous1 = parsed.slice(currentIndex + 1).find((v) => v != null) ?? null;
      const previous3 = parsed.slice(currentIndex + 1).filter((v) => v != null)[2] ?? null;
      const onePeriodChange = current != null && previous1 != null ? current - previous1 : null;
      const threePeriodChange = current != null && previous3 != null ? current - previous3 : null;

      // Screener usually sends latest first; reverse for left→right time progression.
      const trend = parsed
        .filter((v): v is number => v != null)
        .slice(0, 6)
        .reverse();

      return {
        name: row.label,
        current,
        onePeriodChange,
        threePeriodChange,
        trend,
      };
    })
    .sort((a, b) => (b.current ?? -Infinity) - (a.current ?? -Infinity));
}

function MFHoldingsTable({ table }: { table: FinancialTable | null | undefined }) {
  if (!table || !table.rows || table.rows.length === 0) {
    return <div className="p-8 text-center text-zinc-500 text-sm">No mutual fund holdings data available</div>;
  }

  const rows = deriveMFRows(table).slice(0, 12);

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr>
            <th className="text-left px-4 py-3 text-xs text-zinc-500 font-medium border-b border-zinc-800 min-w-[320px]">
              Funding House
            </th>
            <th className="text-right px-4 py-3 text-xs text-zinc-500 font-medium border-b border-zinc-800 whitespace-nowrap">
              Current Holding %
            </th>
            <th className="text-right px-4 py-3 text-xs text-zinc-500 font-medium border-b border-zinc-800 whitespace-nowrap">
              1Q Change
            </th>
            <th className="text-right px-4 py-3 text-xs text-zinc-500 font-medium border-b border-zinc-800 whitespace-nowrap">
              3Q Change
            </th>
            <th className="text-right px-4 py-3 text-xs text-zinc-500 font-medium border-b border-zinc-800 whitespace-nowrap">
              Last 6Q Trend
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, idx) => {
            const c1Class =
              row.onePeriodChange == null
                ? "text-zinc-400"
                : row.onePeriodChange > 0
                  ? "text-lime-400"
                  : row.onePeriodChange < 0
                    ? "text-red-400"
                    : "text-zinc-300";
            const c3Class =
              row.threePeriodChange == null
                ? "text-zinc-400"
                : row.threePeriodChange > 0
                  ? "text-lime-400"
                  : row.threePeriodChange < 0
                    ? "text-red-400"
                    : "text-zinc-300";
            return (
              <tr key={`${row.name}-${idx}`} className="border-b border-zinc-800/50 hover:bg-zinc-800/30 transition-colors">
                <td className="px-4 py-3 text-zinc-200 font-medium">{row.name}</td>
                <td className="px-4 py-3 text-right font-mono text-zinc-100">{fmtPct(row.current)}</td>
                <td className={`px-4 py-3 text-right font-mono ${c1Class}`}>
                  {fmtPct(row.onePeriodChange)}
                </td>
                <td className={`px-4 py-3 text-right font-mono ${c3Class}`}>
                  {fmtPct(row.threePeriodChange)}
                </td>
                <td className="px-4 py-3">
                  <div className="flex justify-end">
                    <Sparkline values={row.trend} />
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function FinancialTable({ table, activeTab }: { table: FinancialTable | null | undefined; activeTab: string }) {
  if (!table || !table.rows || table.rows.length === 0) {
    return (
      <div className="p-8 text-center text-zinc-500 text-sm">
        No {activeTab.replace("_", " ")} data available
      </div>
    );
  }

  function fmt(val: number | string | null | undefined): string {
    if (val === null || val === undefined || val === "") return "—";
    if (typeof val === "number") return val.toLocaleString("en-IN");
    return String(val);
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          <tr>
            <th className="sticky left-0 z-10 bg-zinc-900 text-left px-4 py-3 text-xs text-zinc-500 font-medium border-b border-zinc-800 min-w-[160px] whitespace-nowrap">
              Metric
            </th>
            {((table.columns ?? table.headers) ?? []).map((col, i) => (
              <th
                key={i}
                className="text-right px-4 py-3 text-xs text-zinc-500 font-medium border-b border-zinc-800 whitespace-nowrap"
              >
                {col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {table.rows.map((row, ri) => (
            <tr
              key={ri}
              className="border-b border-zinc-800/50 hover:bg-zinc-800/30 transition-colors"
            >
              <td className="sticky left-0 z-10 bg-zinc-900 px-4 py-3 text-zinc-300 font-medium whitespace-nowrap">
                {row.label}
              </td>
              {(row.values ?? []).map((val, vi) => {
                const isNeg = typeof val === "number" && val < 0;
                return (
                  <td
                    key={vi}
                    className={`px-4 py-3 text-right font-mono text-sm whitespace-nowrap ${
                      isNeg ? "text-red-400" : "text-zinc-100"
                    }`}
                  >
                    {fmt(val)}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function FinancialsSection({ symbol }: FinancialsSectionProps) {
  const [data, setData] = useState<Financials | null>(null);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [activeTab, setActiveTab] = useState("quarterly");
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let active = true;
    const load = async () => {
      setLoading(true);
      setFailed(false);
      const result = await fetchFinancials(symbol);
      if (!active) return;
      setData(result);
      setFailed(result === null);
      setLoading(false);
    };
    void load();
    return () => { active = false; };
  }, [symbol, reloadToken]);

  const tableMap: Record<string, FinancialTable | null | undefined> = {
    quarterly: data?.quarterly_results,
    annual: data?.annual_results,
    balance_sheet: data?.balance_sheet,
    cash_flow: data?.cash_flow,
    shareholding: data?.shareholding,
    mf_holdings: data?.mf_holdings,
  };

  return (
    <section>
      <SectionHeader title="Financials" />

      <div className="space-y-3">
        <Tabs tabs={TABS} active={activeTab} onChange={setActiveTab} />

        <div className="rounded-xl border border-zinc-800 bg-zinc-900 overflow-hidden">
          {loading ? (
            <Skeleton className="h-48 w-full rounded-none" />
          ) : failed ? (
            <div className="p-8 text-center text-red-300 text-sm border border-red-900/60 bg-red-950/20 space-y-3">
              <p>Unable to load financials right now. Check backend connection and try again.</p>
              <button
                onClick={() => setReloadToken((t) => t + 1)}
                className="px-3 py-1.5 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-200 border border-zinc-700"
              >
                Retry
              </button>
            </div>
          ) : activeTab === "mf_holdings" ? (
            <MFHoldingsTable table={tableMap.mf_holdings} />
          ) : (
            <FinancialTable table={tableMap[activeTab]} activeTab={activeTab} />
          )}
        </div>
      </div>
    </section>
  );
}

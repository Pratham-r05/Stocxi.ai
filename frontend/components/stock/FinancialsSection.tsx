"use client";

// FinancialsSection — tabbed financial tables (Quarterly, Annual, BS, CF, Shareholding)
// Color codes cells green/red based on comparison with the previous period.

import { useEffect, useState } from "react";
import { fetchFinancials } from "@/lib/api";
import type { Financials, FinancialTable } from "@/lib/types";
import { Skeleton } from "@/components/ui/Skeleton";
import SectionHeader from "@/components/ui/SectionHeader";
import Tabs from "@/components/ui/Tabs";
import { ExternalLink } from "lucide-react";

interface FinancialsSectionProps {
  symbol: string;
}

const TABS = [
  { id: "quarterly",     label: "Quarterly" },
  { id: "annual",        label: "Annual" },
  { id: "balance_sheet", label: "Balance Sheet" },
  { id: "cash_flow",     label: "Cash Flow" },
  { id: "shareholding",  label: "Shareholding" },
];

// Rows where higher value = bad (expenses, liabilities, etc.)
const HIGHER_IS_BAD = new Set([
  "expenses", "total expenses", "interest", "depreciation",
  "tax", "income tax", "other income", "borrowings", "total liabilities",
  "total debt", "net cash used", "net cash from investing",
]);

function isHigherBad(label: string): boolean {
  const l = label.toLowerCase().trim();
  return HIGHER_IS_BAD.has(l) || l.includes("expense") || l.includes("borrowing") || l.includes("liabilit");
}

function toNum(v: number | string | null | undefined): number | null {
  if (typeof v === "number" && Number.isFinite(v)) return v;
  if (typeof v === "string") {
    const n = Number(v.replace(/,/g, "").trim());
    return Number.isFinite(n) ? n : null;
  }
  return null;
}

function fmt(val: number | string | null | undefined): string {
  if (val == null || val === undefined || val === "") return "—";
  if (typeof val === "number") return val.toLocaleString("en-IN");
  return String(val);
}

function isRawPdfRow(label: string): boolean {
  return label.trim().toLowerCase() === "raw pdf";
}

function isPdfUrl(val: number | string | null | undefined): val is string {
  return typeof val === "string" && /^https?:\/\//i.test(val) && val.toLowerCase().includes(".pdf");
}

function cellColor(
  val: number | string | null | undefined,
  prev: number | string | null | undefined,
  label: string,
): string {
  const cur = toNum(val);
  const prv = toNum(prev);
  if (cur == null || prv == null || prv === 0) return "text-zinc-100";
  const better = isHigherBad(label) ? cur < prv : cur > prv;
  return better ? "text-emerald-400" : "text-red-400";
}

function FinancialTableView({
  table,
  activeTab,
  sourceUrl,
}: {
  table: FinancialTable | null | undefined;
  activeTab: string;
  sourceUrl?: string | null;
}) {
  if (!table || !table.rows || table.rows.length === 0) {
    return (
      <div className="p-8 text-center text-zinc-500 text-sm">
        No {activeTab.replace("_", " ")} data available
      </div>
    );
  }

  const columns = (table.columns ?? table.headers) ?? [];
  const rows = table.rows.filter((row) => {
    if (!isRawPdfRow(row.label)) return true;
    return (row.values ?? []).some(isPdfUrl);
  });

  function comparisonIndex(index: number): number | null {
    if (index <= 0) return null;
    if (activeTab === "quarterly" && index >= 4) return index - 4;
    return index - 1;
  }

  return (
    <div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr>
              <th className="sticky left-0 z-10 bg-zinc-900 text-left px-4 py-3 text-xs text-zinc-500 font-medium border-b border-zinc-800 min-w-[160px] whitespace-nowrap">
                Metric
              </th>
              {columns.map((col, i) => (
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
            {rows.map((row, ri) => (
              <tr
                key={ri}
                className="border-b border-zinc-800/50 hover:bg-zinc-800/30 transition-colors"
              >
                <td className="sticky left-0 z-10 bg-zinc-900 px-4 py-3 text-zinc-300 font-medium whitespace-nowrap">
                  {row.label}
                </td>
                {(row.values ?? []).map((val, vi) => {
                  const compareAt = comparisonIndex(vi);
                  const prevVal = compareAt == null ? null : row.values[compareAt];
                  const color = compareAt != null && prevVal != null
                    ? cellColor(val, prevVal, row.label)
                    : typeof val === "number" && val < 0
                      ? "text-red-400"
                      : "text-zinc-100";
                  return (
                    <td
                      key={vi}
                      className={`px-4 py-3 text-right font-mono text-sm whitespace-nowrap ${color}`}
                    >
                      {isRawPdfRow(row.label) && isPdfUrl(val) ? (
                        <a
                          href={val}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center justify-end gap-1 text-zinc-300 hover:text-white"
                        >
                          PDF
                          <ExternalLink className="w-3 h-3" />
                        </a>
                      ) : (
                        fmt(val)
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {sourceUrl && (
        <div className="px-4 py-3 border-t border-zinc-800 flex items-center justify-end">
          <a
            href={sourceUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 text-xs text-zinc-400 hover:text-zinc-200 transition-colors"
          >
            <ExternalLink className="w-3 h-3" />
            View full report on Screener.in
          </a>
        </div>
      )}
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
      setFailed(result == null);
      setLoading(false);
    };
    void load();
    return () => { active = false; };
  }, [symbol, reloadToken]);

  const sourceUrl = (data as unknown as { source_url?: string })?.source_url ?? null;

  const tableMap: Record<string, FinancialTable | null | undefined> = {
    quarterly:     data?.quarterly_results,
    annual:        data?.annual_results,
    balance_sheet: data?.balance_sheet,
    cash_flow:     data?.cash_flow,
    shareholding:  data?.shareholding,
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
          ) : (
            <FinancialTableView
              table={tableMap[activeTab]}
              activeTab={activeTab}
              sourceUrl={sourceUrl}
            />
          )}
        </div>
      </div>
    </section>
  );
}

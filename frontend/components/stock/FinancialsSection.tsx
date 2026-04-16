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
];

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
            {(table.columns ?? []).map((col, i) => (
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
  const [activeTab, setActiveTab] = useState("quarterly");

  useEffect(() => {
    fetchFinancials(symbol).then((result) => {
      setData(result);
      setLoading(false);
    });
  }, [symbol]);

  const tableMap: Record<string, FinancialTable | null | undefined> = {
    quarterly: data?.quarterly_results,
    annual: data?.annual_results,
    balance_sheet: data?.balance_sheet,
    cash_flow: data?.cash_flow,
    shareholding: data?.shareholding,
  };

  return (
    <section>
      <SectionHeader title="Financials" />

      <div className="space-y-3">
        <Tabs tabs={TABS} active={activeTab} onChange={setActiveTab} />

        <div className="rounded-xl border border-zinc-800 bg-zinc-900 overflow-hidden">
          {loading ? (
            <Skeleton className="h-48 w-full rounded-none" />
          ) : (
            <FinancialTable table={tableMap[activeTab]} activeTab={activeTab} />
          )}
        </div>
      </div>
    </section>
  );
}

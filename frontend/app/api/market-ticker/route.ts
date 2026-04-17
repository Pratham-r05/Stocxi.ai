import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";
export const revalidate = 0;

type IndexTarget = {
  id: string;
  label: string;
  index: string;
};

type MarketTickerItem = {
  id: string;
  label: string;
  symbol: string;
  price: number;
  change: number;
  changePercent: number;
  currency: string;
};

type NseIndexRow = {
  index?: string;
  last?: number | string;
  variation?: number | string;
  percentChange?: number | string;
};

const TARGETS: IndexTarget[] = [
  { id: "nifty50", label: "NIFTY 50", index: "NIFTY 50" },
  { id: "banknifty", label: "NIFTY BANK", index: "NIFTY BANK" },
  {
    id: "financial_services",
    label: "FIN SERVICE",
    index: "NIFTY FINANCIAL SERVICES",
  },
  { id: "niftyit", label: "NIFTY IT", index: "NIFTY IT" },
  { id: "niftyauto", label: "NIFTY AUTO", index: "NIFTY AUTO" },
  { id: "midcap100", label: "MIDCAP 100", index: "NIFTY MIDCAP 100" },
  {
    id: "smallcap100",
    label: "SMALLCAP 100",
    index: "NIFTY SMALLCAP 100",
  },
];

const NSE_ALL_INDICES_URL = "https://www.nseindia.com/api/allIndices";

function isIndianMarketOpen(now = new Date()): boolean {
  const ist = new Date(now.toLocaleString("en-US", { timeZone: "Asia/Kolkata" }));
  const day = ist.getDay();
  if (day === 0 || day === 6) return false;

  const minutes = ist.getHours() * 60 + ist.getMinutes();
  const openMinutes = 9 * 60 + 15;
  const closeMinutes = 15 * 60 + 30;
  return minutes >= openMinutes && minutes <= closeMinutes;
}

function toNumber(value: unknown): number | null {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string") {
    const parsed = Number(value.replace(/,/g, "").trim());
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function toTickerItem(target: IndexTarget, row: NseIndexRow): MarketTickerItem | null {
  const price = toNumber(row.last);
  const change = toNumber(row.variation);
  const changePercent = toNumber(row.percentChange);

  if (
    price === null ||
    change === null ||
    changePercent === null
  ) {
    return null;
  }

  return {
    id: target.id,
    label: target.label,
    symbol: target.label,
    price,
    change,
    changePercent,
    currency: "INR",
  };
}

export async function GET() {
  try {
    const res = await fetch(NSE_ALL_INDICES_URL, {
      cache: "no-store",
      headers: {
        "User-Agent": "Mozilla/5.0",
        Referer: "https://www.nseindia.com/",
        Accept: "application/json, text/plain, */*",
      },
    });

    if (!res.ok) {
      return NextResponse.json(
        {
          items: [],
          updatedAt: new Date().toISOString(),
          marketOpen: isIndianMarketOpen(),
        },
        {
          headers: {
            "Cache-Control": "no-store, max-age=0",
          },
        }
      );
    }

    const payload = (await res.json()) as {
      data?: NseIndexRow[];
    };

    const results = Array.isArray(payload.data) ? payload.data : [];
    const items: MarketTickerItem[] = [];

    for (const target of TARGETS) {
      const row = results.find((entry) => entry.index === target.index);
      if (!row) continue;
      const item = toTickerItem(target, row);
      if (item) items.push(item);
    }

    return NextResponse.json(
      {
        items,
        updatedAt: new Date().toISOString(),
        marketOpen: isIndianMarketOpen(),
      },
      {
        headers: {
          "Cache-Control": "no-store, max-age=0",
        },
      }
    );
  } catch {
    return NextResponse.json(
      {
        items: [],
        updatedAt: new Date().toISOString(),
        marketOpen: isIndianMarketOpen(),
      },
      {
        headers: {
          "Cache-Control": "no-store, max-age=0",
        },
      }
    );
  }
}

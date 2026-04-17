import { NextResponse } from "next/server";

export const dynamic = "force-dynamic";
export const revalidate = 0;

type QuoteTarget = {
  id: string;
  label: string;
  symbol: string;
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

const TARGETS: QuoteTarget[] = [
  { id: "nifty50", label: "NIFTY 50", symbol: "^NSEI" },
  { id: "sensex", label: "SENSEX", symbol: "^BSESN" },
  { id: "banknifty", label: "BANK NIFTY", symbol: "^NSEBANK" },
  { id: "gold", label: "GOLD", symbol: "GC=F" },
  { id: "silver", label: "SILVER", symbol: "SI=F" },
  { id: "usd_inr", label: "USD/INR", symbol: "INR=X" },
  { id: "crude", label: "CRUDE", symbol: "CL=F" },
];

function isIndianMarketOpen(now = new Date()): boolean {
  const ist = new Date(now.toLocaleString("en-US", { timeZone: "Asia/Kolkata" }));
  const day = ist.getDay();
  if (day === 0 || day === 6) return false;

  const minutes = ist.getHours() * 60 + ist.getMinutes();
  const openMinutes = 9 * 60 + 15;
  const closeMinutes = 15 * 60 + 30;
  return minutes >= openMinutes && minutes <= closeMinutes;
}

function toTickerItem(target: QuoteTarget, quote: Record<string, unknown>): MarketTickerItem | null {
  const price = quote.regularMarketPrice;
  const change = quote.regularMarketChange;
  const changePercent = quote.regularMarketChangePercent;

  if (
    typeof price !== "number" ||
    typeof change !== "number" ||
    typeof changePercent !== "number"
  ) {
    return null;
  }

  const currency = typeof quote.currency === "string" ? quote.currency : "INR";

  return {
    id: target.id,
    label: target.label,
    symbol: target.symbol,
    price,
    change,
    changePercent,
    currency,
  };
}

export async function GET() {
  const symbols = TARGETS.map((t) => t.symbol).join(",");
  const url = `https://query1.finance.yahoo.com/v7/finance/quote?symbols=${encodeURIComponent(symbols)}`;

  try {
    const res = await fetch(url, {
      cache: "no-store",
      headers: {
        "User-Agent":
          "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
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
      quoteResponse?: {
        result?: Array<Record<string, unknown>>;
      };
    };

    const results = payload.quoteResponse?.result ?? [];
    const items: MarketTickerItem[] = [];

    for (const target of TARGETS) {
      const quote = results.find((row) => row.symbol === target.symbol);
      if (!quote) continue;
      const item = toTickerItem(target, quote);
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

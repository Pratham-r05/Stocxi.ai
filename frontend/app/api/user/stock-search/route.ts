import { NextRequest, NextResponse } from "next/server";
import { getServerSession } from "next-auth";
import { authOptions } from "@/app/api/auth/[...nextauth]/route";
import {
  getUserStockSearches,
  recordUserStockSearch,
} from "@/lib/userStore";

function isValidSymbol(symbol: string): boolean {
  return /^[A-Z0-9.-]{1,20}$/.test(symbol);
}

export async function POST(req: NextRequest) {
  const session = await getServerSession(authOptions);
  const email = session?.user?.email;
  if (!email) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const body = await req.json().catch(() => null);
  const symbol = typeof body?.symbol === "string" ? body.symbol.trim().toUpperCase() : "";

  if (!symbol || !isValidSymbol(symbol)) {
    return NextResponse.json({ error: "Invalid stock symbol" }, { status: 400 });
  }

  const ok = await recordUserStockSearch(email, symbol);
  if (!ok) {
    return NextResponse.json({ error: "Failed to save stock search" }, { status: 500 });
  }

  return NextResponse.json({ success: true });
}

export async function GET() {
  const session = await getServerSession(authOptions);
  const email = session?.user?.email;
  if (!email) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const searches = await getUserStockSearches(email);
  return NextResponse.json({ searches });
}

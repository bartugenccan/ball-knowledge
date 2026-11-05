import { type NextRequest, NextResponse } from "next/server";
import { GATE_COOKIE, cookieIsValid, gateIsOn } from "@/lib/gate";

export function proxy(request: NextRequest) {
  if (!gateIsOn() || cookieIsValid(request.cookies.get(GATE_COOKIE)?.value)) return NextResponse.next();
  const url = request.nextUrl.clone();
  url.searchParams.delete("_rsc");
  const next = url.pathname + url.search;
  url.pathname = "/giris";
  url.search = `?next=${encodeURIComponent(next)}`;
  return NextResponse.redirect(url);
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|icon\\.svg|giris).*)"],
};

import { NextResponse } from "next/server";
import { GATE_COOKIE, GATE_MAX_AGE, gateToken, passwordIsRight, safeNext } from "@/lib/gate";

export async function POST(request: Request) {
  const form = await request.formData();
  const next = safeNext(form.get("next"));
  const password = form.get("password");
  if (typeof password !== "string" || !passwordIsRight(password)) {
    return NextResponse.redirect(new URL(`/giris?hata=1&next=${encodeURIComponent(next)}`, request.url), 303);
  }
  const response = NextResponse.redirect(new URL(next, request.url), 303);
  response.cookies.set(GATE_COOKIE, gateToken(), { httpOnly: true, secure: process.env.NODE_ENV === "production", sameSite: "lax", maxAge: GATE_MAX_AGE, path: "/" });
  return response;
}

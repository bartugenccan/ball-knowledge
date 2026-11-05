import { createHmac, timingSafeEqual } from "node:crypto";

/** One shared password for the test group. Without SITE_PASSWORD the site is open, as in local work. */
export const GATE_COOKIE = "bk_gate";
export const GATE_MAX_AGE = 60 * 60 * 24 * 60;

function sign(value: string): Buffer {
  const secret = process.env.SITE_COOKIE_SECRET;
  if (!secret) throw new Error("SITE_PASSWORD needs SITE_COOKIE_SECRET");
  return createHmac("sha256", secret).update(value).digest();
}

function same(a: Buffer, b: Buffer): boolean {
  return a.length === b.length && timingSafeEqual(a, b);
}

export function gateIsOn(): boolean {
  return Boolean(process.env.SITE_PASSWORD);
}

export function passwordIsRight(input: string): boolean {
  return same(sign(input), sign(process.env.SITE_PASSWORD ?? ""));
}

/** The cookie holds a signature of the password, not the password. Changing the password signs everyone out. */
export function gateToken(): string {
  return sign(process.env.SITE_PASSWORD ?? "").toString("hex");
}

export function cookieIsValid(value: string | undefined): boolean {
  return Boolean(value) && same(Buffer.from(value as string, "hex"), Buffer.from(gateToken(), "hex"));
}

/** Where to go after signing in. It comes from the URL, so it may only be a page of this site. */
export function safeNext(value: unknown): string {
  return typeof value === "string" && /^\/(?![/\\])/.test(value) && !value.startsWith("/giris") ? value : "/";
}

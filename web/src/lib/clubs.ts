/**
 * The palette comes from the clubs, not from a brand. p = main colour, s = second colour, used
 * for text on p when it is readable. Colours are the clubs' public identity, not logos; shades
 * are approximate. Everything else (tints, readable text, stand seats) is computed so that no
 * combination can fail contrast.
 */
const CLUBS: Record<string, { p: string; s: string; alt?: string }> = {
  ASV: { p: "#111111", s: "#ffffff" }, // black and white since the 2021 rebrand, green before that
  BAR: { p: "#a50044", s: "#ffffff", alt: "#edbb00" },
  BAS: { p: "#003a70", s: "#ffffff", alt: "#d50032" },
  BER: { p: "#ffd500", s: "#00387b" },
  BES: { p: "#111111", s: "#ffffff" },
  DUB: { p: "#6b4a2f", s: "#ffffff" },
  HTA: { p: "#ce1126", s: "#ffffff" },
  IST: { p: "#0d2b6b", s: "#ffffff", alt: "#e30613" },
  MAD: { p: "#00529f", s: "#ffffff", alt: "#febe10" },
  MCO: { p: "#d4021d", s: "#ffffff" },
  MIL: { p: "#e2001a", s: "#ffffff" },
  MUN: { p: "#dc052d", s: "#ffffff" },
  OLY: { p: "#d0021b", s: "#ffffff" },
  PAM: { p: "#e55a10", s: "#111111" },
  PAN: { p: "#007a33", s: "#ffffff" },
  PAR: { p: "#111111", s: "#ffffff" },
  PRS: { p: "#1b2f8f", s: "#ffffff", alt: "#e30613" },
  RED: { p: "#d2111b", s: "#ffffff" },
  TEL: { p: "#ffd200", s: "#0033a0" },
  ULK: { p: "#0b1f5b", s: "#ffed00" },
  VIR: { p: "#111111", s: "#ffffff" },
  ZAL: { p: "#006a44", s: "#ffffff" },
};

const PAGE_LIGHT = "#eeeeea";
const PAGE_DARK = "#1a1a18";
const GREY = "#85857d";

const rgb = (h: string) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
const toHex = (c: number[]) => `#${c.map((v) => Math.round(v).toString(16).padStart(2, "0")).join("")}`;
const mix = (a: string, b: string, t: number) => {
  const x = rgb(a);
  const y = rgb(b);
  return toHex(x.map((v, i) => v + (y[i] - v) * t));
};
const lum = (h: string) => {
  const [r, g, b] = rgb(h).map((v) => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
};
export const contrast = (a: string, b: string) => {
  const [x, y] = [lum(a), lum(b)];
  return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05);
};
const bestInk = (bg: string, prefer?: string) => {
  if (prefer && contrast(bg, prefer) >= 4.5) return prefer;
  return contrast(bg, "#ffffff") >= contrast(bg, "#111111") ? "#ffffff" : "#111111";
};
/** Pushes a colour towards black or white until it reads as small text on the given page. */
const readableOn = (color: string, page: string) => {
  const target = lum(page) > 0.5 ? "#000000" : "#ffffff";
  let c = color;
  for (let t = 0.1; contrast(c, page) < 4.5 && t <= 1; t += 0.1) c = mix(color, target, t);
  return c;
};

export type ClubStyle = Record<string, string> & React.CSSProperties;

const cache = new Map<string, ClubStyle>();

/** CSS variables for a club. Put on an element with class "club". Unknown clubs stay neutral. */
export function clubVars(code: string | undefined): ClubStyle | undefined {
  if (!code) return undefined;
  const hit = cache.get(code);
  if (hit) return hit;
  const c = CLUBS[code];
  if (!c) return undefined;
  const ink = bestInk(c.p, c.s);
  // the second tier of a rating: the club colour, thinned out with paper
  let paper = 0.45;
  let mid = mix(c.p, "#f7f7f4", paper);
  // mid-greys read badly with both black and white text: step back until one of them passes
  while (contrast(mid, bestInk(mid)) < 4.5 && paper > 0.1) {
    paper -= 0.03;
    mid = mix(c.p, "#f7f7f4", paper);
  }
  const toward = lum(c.p) < 0.5 ? "#ffffff" : "#000000";
  const showOn = (page: string) => {
    if (contrast(c.p, page) >= 3) return c.p;
    // on a dark page a navy should stay blue, not turn into its white text colour; true blacks do go white
    const [r, g, b] = rgb(c.p);
    if (lum(page) < 0.5 && Math.max(r, g, b) - Math.min(r, g, b) > 24) {
      for (let t = 0.1; t <= 0.9; t += 0.05) {
        const lifted = mix(c.p, "#ffffff", t);
        if (contrast(lifted, page) >= 3) return lifted;
      }
    }
    return contrast(ink, page) >= 3 ? ink : lum(page) > 0.5 ? "#111111" : "#f7f7f4";
  };
  const muted = mix(ink, c.p, 0.2);
  const accent = c.alt && contrast(c.alt, c.p) >= 3 ? c.alt : ink;
  const vars = {
    "--club": c.p,
    "--club-ink": ink,
    "--club-mid": mid,
    "--club-mid-ink": bestInk(mid),
    "--club-l": showOn(PAGE_LIGHT),
    "--club-d": showOn(PAGE_DARK),
    "--club-t-l": readableOn(showOn(PAGE_LIGHT), PAGE_LIGHT),
    "--club-t-d": readableOn(showOn(PAGE_DARK), PAGE_DARK),
    "--stand": c.p,
    "--stand-ink": ink,
    "--stand-muted": contrast(muted, c.p) >= 4.5 ? muted : ink,
    "--stand-seat": mix(c.p, toward, 0.1),
    "--stand-seat-2": mix(c.p, toward, 0.04),
    "--stand-seat-3": mix(c.p, toward, 0.17),
    "--stand-hot": ink,
    "--stand-amber": accent,
  } as ClubStyle;
  cache.set(code, vars);
  return vars;
}

/** Main colour of every club: the stadium wave is made of all of them. */
export const allClubColors = () => Object.values(CLUBS).map((c) => c.p);

/**
 * Head-to-head colours. Two red clubs cannot both wear red, so the second side switches to its
 * other colours, like an away kit, and to ink if those do not help either. Returns the variables
 * for a wrapper with class "pair".
 */
export function clubPair(a: string, b: string): ClubStyle {
  const far = (x: string, y: string) => {
    const [p, q] = [rgb(x), rgb(y)];
    return Math.hypot(p[0] - q[0], p[1] - q[1], p[2] - q[2]) > 100;
  };
  const side = (code: string, name: "a" | "b", other?: { l: string; d: string }) => {
    const c = CLUBS[code];
    const pick = (page: string, fallback: string, avoid?: string) => {
      // grey is the last resort: it stays readable and differs from any dark or bright club colour
      const options = c ? [c.p, c.alt, c.s, fallback, GREY] : [fallback, GREY];
      return options.find((o): o is string => Boolean(o) && contrast(o as string, page) >= 3 && (!avoid || far(o as string, avoid))) ?? GREY;
    };
    const l = pick(PAGE_LIGHT, "#141414", other?.l);
    const d = pick(PAGE_DARK, "#efefe9", other?.d);
    return {
      l,
      d,
      vars: {
        [`--side-${name}-l`]: l,
        [`--side-${name}-d`]: d,
        [`--side-${name}-i-l`]: bestInk(l),
        [`--side-${name}-i-d`]: bestInk(d),
        [`--side-${name}-t-l`]: readableOn(l, PAGE_LIGHT),
        [`--side-${name}-t-d`]: readableOn(d, PAGE_DARK),
      },
    };
  };
  const sa = side(a, "a");
  const sb = side(b, "b", sa);
  return { ...sa.vars, ...sb.vars } as ClubStyle;
}

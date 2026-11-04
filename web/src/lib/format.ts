import type { AttributeMeta, Group, Rating, Source } from "./types";

export const GROUP_LABEL: Record<Group, string> = {
  hucum: "Hücum",
  savunma: "Savunma",
  zihinsel: "Yük & İstikrar",
};

export const SOURCE_LABEL: Record<Source, string> = {
  veri: "Veriden",
  turetilmis: "Türetilmiş",
  tahmini: "Tahmini",
};

/** The hint as plain text, for places that can only show a native tooltip (rotated table headers). */
export function hintText(a: AttributeMeta): string {
  return a.hint ? [a.hint.what, a.hint.how, a.hint.note].filter(Boolean).join("\n") : a.description;
}

export const SOURCE_HINT: Record<Source, string> = {
  veri: "Doğrudan maç istatistiklerinden hesaplanır.",
  turetilmis: "Play-by-play'den türetilir (beşliler, stint, skor durumu).",
  tahmini: "Açık veride doğrudan yok; sahadaki beşli verisinden dolaylı tahmin.",
};

/** Tone bucket for a 1–20 attribute. Use as r-* (text), tile-r-* (card), heat-r-* (fill). */
export function tone(v: number): string {
  if (v >= 17) return "r-elite";
  if (v >= 14) return "r-good";
  if (v >= 10) return "r-avg";
  if (v >= 6) return "r-low";
  return "r-poor";
}

/** Fill colour for one position on the 1-20 scale (lamps and arena seats). */
export function heatVar(n: number): string {
  return `var(--heat-${tone(n).slice(2)})`;
}

/** Tone for a Düşük / Orta / Yüksek label; statements like "Az veri" stay neutral. */
export function labelTone(label: string): string {
  return label === "Yüksek" ? "r-good" : label === "Orta" ? "r-avg" : label === "Düşük" ? "r-low" : "text-muted";
}

// Not single letters: in the condensed display face a lone "O" reads as a rating of 0.
const SHORT_LABEL: Record<string, string> = { Yüksek: "Yük", Orta: "Ort", Düşük: "Düş" };

/** Short form of a tier for table cells; a statement becomes a dash, with the words in the title. */
export function shortLabel(label: string): string {
  return SHORT_LABEL[label] ?? "–";
}

/** Tone bucket for a 1–10 match rating. */
export function gameTone(v: number): string {
  if (v >= 8) return "r-elite";
  if (v >= 7) return "r-good";
  if (v >= 6) return "r-avg";
  if (v >= 5) return "r-low";
  return "r-poor";
}

/** Radar axes: each is the mean of a few attributes. */
export const RADAR_AXES: { label: string; note: string; keys: string[] }[] = [
  { label: "Pota hücumu", note: "Bitiricilik ve Faul Alma ortalaması", keys: ["finishing", "drawing_fouls"] },
  { label: "Dış şut", note: "Üçlük, Orta Mesafe ve Serbest Atış ortalaması", keys: ["three_point", "mid_range", "free_throw"] },
  { label: "Oyun kurma", note: "Pas, Top Güvenliği ve Şut Yaratma ortalaması", keys: ["passing", "ball_security", "shot_creation"] },
  { label: "Ribaund", note: "Hücum ve Savunma Ribaundu ortalaması", keys: ["off_rebounding", "def_rebounding"] },
  { label: "Savunma", note: "Top Çalma, Blok, Pota Koruma, Çevre Savunması, Savunma Etkisi ve Faul Disiplini ortalaması", keys: ["steals", "shot_blocking", "rim_protection", "perimeter_defense", "team_defense", "discipline"] },
  { label: "Yük & istikrar", note: "Oyun Yükü ve İstikrar ortalaması", keys: ["stamina", "consistency"] },
];

export function radarValues(ratings: Rating[]): { label: string; note: string; value: number }[] {
  const by = new Map(ratings.map((r) => [r.key, r.value]));
  return RADAR_AXES.map((a) => {
    const vals = a.keys.map((k) => by.get(k)).filter((v): v is number => v !== undefined);
    return { label: a.label, note: a.note, value: vals.length ? vals.reduce((s, v) => s + v, 0) / vals.length : 10 };
  });
}

/** Unrounded overall, for ranking. Several players round to the same headline number. */
export function overallExact(ratings: Rating[]): number {
  const axes = radarValues(ratings);
  return axes.reduce((s, a) => s + a.value, 0) / axes.length;
}

/** Headline number: mean of the radar axes, so no single group dominates. */
export function overall(ratings: Rating[]): number {
  return Math.round(overallExact(ratings));
}

// Player names are mostly non-Turkish: locale-free casing keeps "MILLER" -> "Miller", not "Mıller".
const cap = (s: string) =>
  s
    .toLowerCase()
    .replace(/(^|[\s'.-])(\p{L})/gu, (_, sep: string, ch: string) => sep + ch.toUpperCase())
    .replace(/\b(Ii|Iii|Iv)\b/g, (r) => r.toUpperCase()); // "Clark Iii" -> "Clark III"

/** Feed names are "LAST, FIRST" in capitals. */
export function nameParts(raw: string): { first: string; last: string } {
  const [last, first] = raw.split(",").map((s) => s.trim());
  return { first: first ? cap(first) : "", last: cap(last) };
}

export function properName(raw: string): string {
  const { first, last } = nameParts(raw);
  return first ? `${first} ${last}` : last;
}

export const pct = (v: number, digits = 1) => `${(100 * v).toFixed(digits)}%`;

export function seasonLabel(code: string): string {
  const y = Number(code.slice(1));
  return Number.isFinite(y) ? `${y}-${String(y + 1).slice(2)}` : code;
}

const MONTHS = ["Oca", "Şub", "Mar", "Nis", "May", "Haz", "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara"];
export function monthLabel(m: string): string {
  const [y, mm] = m.split("-");
  return `${MONTHS[Number(mm) - 1]} ${y}`;
}

export const ZONE_LABEL: Record<string, string> = {
  inside: "Pota + boyalı alan",
  // the simulator's sets still name these two separately
  rim: "Pota altı",
  paint: "Boyalı alan",
  mid: "Orta mesafe",
  corner3: "Köşe üçlük",
  above_break3: "Üçlük",
  three: "Üçlük (tümü)",
  ft: "Serbest atış",
};

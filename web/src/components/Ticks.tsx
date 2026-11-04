/**
 * A rating as 20 lamps. Each lamp keeps the colour of its own position on the scale, so a high
 * rating literally reaches the hot end, and they light one at a time.
 *
 * Two elements per rail, not twenty: the lamps are a gradient cut by a mask and revealed with a
 * stepped clip, so a page with 80 rails stays light.
 */
export function Ticks({ value, row = 0, color, rtl, dim }: { value: number; row?: number; color?: string; rtl?: boolean; dim?: boolean }) {
  const lit = Math.max(0, Math.min(20, Math.round(value)));
  return (
    <div aria-hidden className={`rail ${rtl ? "rail-rtl" : ""}`} style={{ opacity: dim ? 0.45 : undefined }}>
      <i style={{ ["--v" as string]: lit, ["--row" as string]: row, ...(color ? { background: color } : {}) }} />
    </div>
  );
}

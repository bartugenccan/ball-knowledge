// Court geometry in centimetres (FIBA). Feed coordinates have the basket at (0,0);
// y is shifted so the baseline sits at the top of the drawing.
const BASELINE = 157.5;
export const COURT_W = 1500;
export const COURT_H = 1000; // 10 m from the baseline; deep heaves are clipped
export const tx = (x: number) => x + COURT_W / 2;
export const ty = (y: number) => y + BASELINE;

/** Half-court line drawing. Colours come from the caller so it works on any block. */
export function CourtLines({ stroke, rim, paint }: { stroke: string; rim: string; paint: string }) {
  const corner = Math.sqrt(675 ** 2 - 660 ** 2);
  return (
    <g fill="none" stroke={stroke} strokeWidth={5}>
      <rect x={tx(-245)} y={0} width={490} height={580} fill={paint} />
      <circle cx={tx(0)} cy={580} r={180} />
      <path d={`M ${tx(-660)} 0 L ${tx(-660)} ${ty(corner)} A 675 675 0 0 0 ${tx(660)} ${ty(corner)} L ${tx(660)} 0`} />
      <path d={`M ${tx(-125)} ${ty(0)} A 125 125 0 0 0 ${tx(125)} ${ty(0)}`} />
      <line x1={tx(-90)} x2={tx(90)} y1={ty(-37.5)} y2={ty(-37.5)} strokeWidth={8} />
      <circle cx={tx(0)} cy={ty(0)} r={22.5} stroke={rim} strokeWidth={7} />
    </g>
  );
}

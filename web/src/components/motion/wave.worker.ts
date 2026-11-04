// Draws the route wave off the main thread, so it stays smooth while the next page mounts.
const CELL = 46;
const LIFE = 300;

type Msg =
  | { type: "init"; canvas: OffscreenCanvas; colors: string[] }
  | { type: "play"; width: number; height: number; dpr: number };

const scope = self as unknown as { onmessage: ((e: MessageEvent<Msg>) => void) | null };
let canvas: OffscreenCanvas;
let ctx: OffscreenCanvasRenderingContext2D;
let colors: string[] = [];
let raf = 0;

scope.onmessage = ({ data: m }) => {
  if (m.type === "init") {
    canvas = m.canvas;
    ctx = canvas.getContext("2d")!;
    colors = m.colors;
    return;
  }
  cancelAnimationFrame(raf);
  const { width: W, height: H, dpr } = m;
  canvas.width = W * dpr;
  canvas.height = H * dpr;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  const cols = Math.ceil(W / CELL);
  const rows = Math.ceil(H / CELL);
  const cells: { x: number; y: number; at: number; c: string }[] = [];
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      // keep it a wave, not a wipe: only some of the crowd stands up
      if (Math.random() < 0.28) continue;
      cells.push({
        x: c * CELL,
        y: r * CELL,
        at: (c / cols) * 420 + (r / rows) * 120 + Math.random() * 60,
        c: colors[Math.floor(Math.random() * colors.length)],
      });
    }
  }
  const t0 = performance.now();
  const end = 420 + 120 + 60 + LIFE;
  const frame = (now: number) => {
    const t = now - t0;
    ctx.clearRect(0, 0, W, H);
    for (const k of cells) {
      const p = (t - k.at) / LIFE;
      if (p <= 0 || p >= 1) continue;
      const h = (CELL - 2) * Math.sin(Math.PI * p);
      ctx.fillStyle = k.c;
      ctx.fillRect(k.x, k.y + (CELL - h) / 2, CELL - 2, h);
    }
    if (t < end) raf = requestAnimationFrame(frame);
    else {
      // shrink the idle layer so a full-screen canvas costs no memory between waves
      canvas.width = 1;
      canvas.height = 1;
    }
  };
  raf = requestAnimationFrame(frame);
};

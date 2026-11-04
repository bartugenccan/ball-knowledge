/**
 * The crowd of cards, independent of React and of the DOM, so it can run in a worker and keep
 * moving while the page is busy mounting. Only cards that are mid-flip get repainted: an idle
 * stand touches a handful of cards per second instead of thousands per frame.
 */

const FLIP_MS = 300;
const SWEEP_MS = 1100;
const RIPPLE_MS = 340;
const FAR = 0.62; // how much smaller the top row is than the bottom row
const AISLE_EVERY = 26;
const CROWD_COLOURS = 3; // the first entries of the palette are crowd colours

type Ctx = CanvasRenderingContext2D | OffscreenCanvasRenderingContext2D;

export type StandConfig = {
  width: number;
  height: number;
  dpr: number;
  palette: string[];
  /** One palette index and one rasterised text per frame, at standGrid() resolution. */
  tones: number[];
  bitmaps: Uint8Array[];
  hold: number;
  /** Reduced motion: paint this frame once and never animate. */
  staticFrame: number | null;
};

export type StandHandle = {
  layout: (cfg: StandConfig) => void;
  pointer: (x: number, y: number, radius: number) => void;
  visible: (on: boolean) => void;
  destroy: () => void;
};

/** Size of the stand for a canvas size. The main thread needs it to rasterise text. */
export function standGrid(W: number, H: number) {
  const cell = Math.max(6.5, Math.min(13, W / 118));
  const rowInfo: { y: number; h: number; s: number }[] = [];
  let y = 0;
  let gapDone = false;
  while (y < H) {
    const s = FAR + (1 - FAR) * (y / H);
    const h = cell * s;
    rowInfo.push({ y, h, s });
    y += h;
    if (!gapDone && y > H * 0.4) {
      y += h * 0.9; // the walkway between the lower and upper tier
      gapDone = true;
    }
  }
  return { cell, rowInfo, rows: rowInfo.length, cols: Math.ceil(W / (cell * FAR)) + 2, vcols: Math.floor(W / cell) };
}

export function createStand(canvas: HTMLCanvasElement | OffscreenCanvas, first: StandConfig, onFrame: (i: number) => void): StandHandle {
  const ctx = canvas.getContext("2d") as Ctx;
  let cfg = first;
  let grid = standGrid(cfg.width, cfg.height);
  let N = 0;
  let X = new Float32Array(0);
  let Y = new Float32Array(0);
  let CW = new Float32Array(0);
  let CH = new Float32Array(0);
  let CC = new Int16Array(0);
  let CR = new Int16Array(0);
  let cur = new Uint8Array(0);
  let next = new Uint8Array(0);
  let crowd = new Uint8Array(0);
  let start = new Float64Array(0);
  let rip = new Float64Array(0);
  let lookup = new Int32Array(0);
  // cards currently moving, so a frame never has to scan the whole stand
  let active = new Int32Array(0);
  let isActive = new Uint8Array(0);
  let activeCount = 0;

  let frameIdx = 0;
  let dir = 1;
  let nextAt = Infinity;
  let raf = 0;
  let running = false;
  let lastAmbient = 0;
  let lastFill = -1;

  const wake = (i: number) => {
    if (!isActive[i]) {
      isActive[i] = 1;
      active[activeCount++] = i;
    }
  };

  function build() {
    canvas.width = Math.round(cfg.width * cfg.dpr);
    canvas.height = Math.round(cfg.height * cfg.dpr);
    ctx.setTransform(cfg.dpr, 0, 0, cfg.dpr, 0, 0);
    grid = standGrid(cfg.width, cfg.height);
    const { rowInfo, rows, cols, cell } = grid;
    lookup = new Int32Array(rows * cols).fill(-1);
    const xs: number[] = [];
    const ys: number[] = [];
    const cw: number[] = [];
    const ch: number[] = [];
    const cc: number[] = [];
    const cr: number[] = [];
    for (let ri = 0; ri < rows; ri++) {
      const { y, h, s } = rowInfo[ri];
      const w = cell * s;
      for (let c = 0; c < cols; c++) {
        const fromMid = c - Math.floor(cols / 2);
        if (Math.abs(fromMid) % AISLE_EVERY === Math.floor(AISLE_EVERY / 2)) continue;
        const x = cfg.width / 2 + fromMid * w;
        if (x + w < 0 || x > cfg.width) continue;
        lookup[ri * cols + c] = xs.length;
        xs.push(x);
        ys.push(y);
        cw.push(w * 0.84);
        ch.push(h * 0.84);
        cc.push(c);
        cr.push(ri);
      }
    }
    N = xs.length;
    X = Float32Array.from(xs);
    Y = Float32Array.from(ys);
    CW = Float32Array.from(cw);
    CH = Float32Array.from(ch);
    CC = Int16Array.from(cc);
    CR = Int16Array.from(cr);
    crowd = new Uint8Array(N);
    for (let i = 0; i < N; i++) crowd[i] = Math.random() < 0.55 ? 0 : Math.random() < 0.6 ? 1 : 2;
    cur = crowd.slice();
    next = crowd.slice();
    start = new Float64Array(N).fill(-1);
    rip = new Float64Array(N).fill(-1);
    active = new Int32Array(N);
    isActive = new Uint8Array(N);
    activeCount = 0;
  }

  function showFrame(idx: number, now: number, instant = false) {
    const bits = cfg.bitmaps[idx];
    const { cols, vcols, rows } = grid;
    if (!bits || vcols < 1 || rows < 1) return;
    onFrame(idx);
    const tone = cfg.tones[idx];
    dir = -dir;
    const midCol = Math.floor(cols / 2);
    const halfV = Math.floor(vcols / 2);
    for (let i = 0; i < N; i++) {
      const bx = CC[i] - midCol + halfV;
      const by = CR[i];
      const lit = bx >= 0 && bx < vcols && bits[by * vcols + bx] === 1;
      let target = lit ? tone : crowd[i];
      const roll = Math.random();
      if (lit && roll < 0.014) target = crowd[i]; // someone is holding the wrong side
      else if (!lit && roll < 0.003) target = tone; // someone is early, or just wrong
      if (roll > 0.994) target = crowd[i]; // empty seat
      next[i] = target;
      if (instant) {
        cur[i] = target;
        start[i] = -1;
        continue;
      }
      const nx = bx / Math.max(1, vcols);
      const px = dir > 0 ? nx : 1 - nx;
      let delay = (px * 0.82 + (1 - by / rows) * 0.18) * SWEEP_MS + Math.random() * 110;
      if (Math.random() < 0.025) delay += 350 + Math.random() * 800; // slow to notice
      start[i] = now + delay;
      wake(i);
    }
    nextAt = cfg.bitmaps.length > 1 ? now + SWEEP_MS + cfg.hold : Infinity;
  }

  const fill = (c: number) => {
    if (c !== lastFill) {
      ctx.fillStyle = cfg.palette[c];
      lastFill = c;
    }
  };

  function paintAll() {
    ctx.clearRect(0, 0, cfg.width, cfg.height);
    lastFill = -1;
    for (let k = 0; k < cfg.palette.length; k++) {
      ctx.fillStyle = cfg.palette[k];
      for (let i = 0; i < N; i++) if (cur[i] === k) ctx.fillRect(X[i], Y[i], CW[i], CH[i]);
    }
    lastFill = -1;
  }

  function loop(now: number) {
    raf = requestAnimationFrame(loop);
    if (now > nextAt) {
      frameIdx = (frameIdx + 1) % cfg.bitmaps.length;
      showFrame(frameIdx, now);
    }
    // a restless crowd: a few people fiddle with their cards between frames
    if (now - lastAmbient > 170 && N > 0) {
      lastAmbient = now;
      for (let k = 0; k < 5; k++) {
        const i = Math.floor(Math.random() * N);
        if (start[i] < 0 && cur[i] < CROWD_COLOURS) {
          next[i] = crowd[i];
          start[i] = now;
          wake(i);
        }
      }
    }
    for (let a = activeCount - 1; a >= 0; a--) {
      const i = active[a];
      let sy = 1;
      let color = cur[i];
      let busy = false;
      let touched = false;

      const st = start[i];
      if (st >= 0) {
        busy = true;
        if (now >= st) {
          touched = true;
          const p = (now - st) / FLIP_MS;
          if (p >= 1) {
            cur[i] = next[i];
            color = next[i];
            start[i] = -1;
            busy = false;
          } else {
            sy = Math.abs(Math.cos(Math.PI * p));
            color = p < 0.5 ? cur[i] : next[i];
          }
        }
      }
      const rs = rip[i];
      if (rs >= 0) {
        busy = true;
        if (now >= rs) {
          touched = true;
          const q = (now - rs) / RIPPLE_MS;
          if (q >= 1) rip[i] = -1;
          else {
            sy *= Math.abs(Math.cos(Math.PI * q));
            if (q > 0.5 && q < 0.85 && color < CROWD_COLOURS) color = CROWD_COLOURS; // the back of the card catches the light
          }
        }
        if (rip[i] < 0 && start[i] < 0) busy = false;
      }
      if (touched) {
        ctx.clearRect(X[i] - 0.5, Y[i] - 0.5, CW[i] + 1, CH[i] + 1);
        fill(color);
        const h = CH[i] * sy;
        ctx.fillRect(X[i], Y[i] + (CH[i] - h) / 2, CW[i], h);
      }
      if (!busy) {
        isActive[i] = 0;
        active[a] = active[--activeCount];
      }
    }
  }

  function setRunning(on: boolean) {
    if (on === running) return;
    running = on;
    if (on) raf = requestAnimationFrame(loop);
    else cancelAnimationFrame(raf);
  }

  function layout(nextCfg: StandConfig, instant: boolean) {
    cfg = nextCfg;
    build();
    const only = cfg.staticFrame;
    if (only !== null) {
      showFrame(only, 0, true);
      paintAll();
      return;
    }
    if (instant) {
      showFrame(frameIdx, performance.now(), true);
      paintAll();
    } else {
      paintAll();
      showFrame(0, performance.now() + 150);
      setRunning(true);
    }
  }

  layout(first, false);

  return {
    layout: (c) => layout(c, true),
    visible: (on) => {
      if (cfg.staticFrame === null) setRunning(on);
    },
    pointer: (px, py, radius) => {
      if (cfg.staticFrame !== null) return;
      const { rowInfo, rows, cols, cell } = grid;
      const now = performance.now();
      let ri = rows - 1;
      for (let r = 0; r < rows; r++) {
        if (rowInfo[r].y + rowInfo[r].h > py) {
          ri = r;
          break;
        }
      }
      const c0 = Math.round((px - cfg.width / 2) / (cell * rowInfo[ri].s)) + Math.floor(cols / 2);
      for (let r = Math.max(0, ri - radius); r <= Math.min(rows - 1, ri + radius); r++) {
        for (let c = Math.max(0, c0 - radius); c <= Math.min(cols - 1, c0 + radius); c++) {
          const i = lookup[r * cols + c];
          if (i < 0) continue;
          const d = Math.hypot(r - ri, c - c0);
          if (d > radius) continue;
          if (rip[i] < 0 || rip[i] + RIPPLE_MS < now) {
            rip[i] = now + d * 26;
            wake(i);
          }
        }
      }
    },
    destroy: () => setRunning(false),
  };
}

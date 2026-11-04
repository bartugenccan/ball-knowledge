import { createStand, type StandConfig, type StandHandle } from "./stand-engine";

type Msg =
  | { type: "init"; canvas: OffscreenCanvas; cfg: StandConfig }
  | { type: "layout"; cfg: StandConfig }
  | { type: "pointer"; x: number; y: number; radius: number }
  | { type: "visible"; on: boolean }
  | { type: "destroy" };

const scope = self as unknown as { postMessage: (m: unknown) => void; close: () => void; onmessage: ((e: MessageEvent<Msg>) => void) | null };
let stand: StandHandle | undefined;

scope.onmessage = ({ data: m }) => {
  if (m.type === "init") stand = createStand(m.canvas, m.cfg, (i) => scope.postMessage({ type: "frame", i }));
  else if (m.type === "layout") stand?.layout(m.cfg);
  else if (m.type === "pointer") stand?.pointer(m.x, m.y, m.radius);
  else if (m.type === "visible") stand?.visible(m.on);
  else {
    stand?.destroy();
    scope.close();
  }
};

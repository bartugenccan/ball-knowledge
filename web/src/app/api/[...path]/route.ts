const API_URL = process.env.API_URL ?? "http://127.0.0.1:8000";

type Context = { params: Promise<{ path: string[] }> };

/** Browser calls reach the Python engine through here, so the API key never leaves the server. */
async function forward(request: Request, { params }: Context): Promise<Response> {
  const { path } = await params;
  const url = new URL(`/api/${path.map(encodeURIComponent).join("/")}`, API_URL);
  url.search = new URL(request.url).search;
  const headers = new Headers({ "content-type": "application/json" });
  if (process.env.BK_API_KEY) headers.set("x-bk-key", process.env.BK_API_KEY);
  const res = await fetch(url, { method: request.method, headers, body: request.method === "POST" ? await request.text() : undefined });
  return new Response(await res.text(), { status: res.status, headers: { "content-type": res.headers.get("content-type") ?? "application/json" } });
}

export const GET = forward;

/** The simulator is the only thing the browser may post. */
export async function POST(request: Request, context: Context): Promise<Response> {
  const { path } = await context.params;
  if (path.join("/") !== "simulate") return Response.json({ detail: "not found" }, { status: 404 });
  return forward(request, context);
}

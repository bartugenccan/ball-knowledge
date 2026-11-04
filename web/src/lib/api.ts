import "server-only";
import { notFound } from "next/navigation";
import { cache } from "react";
import type { Meta, PlayerDetail, PlayerRow, RosterRow, TeamSummary } from "./types";

const API_URL = process.env.API_URL ?? "http://127.0.0.1:8000";

async function get<T>(path: string, params: Record<string, string | undefined> = {}): Promise<T> {
  const url = new URL(path, API_URL);
  for (const [k, v] of Object.entries(params)) if (v) url.searchParams.set(k, v);
  const res = await fetch(url);
  if (res.status === 404) notFound();
  if (!res.ok) throw new Error(`API ${res.status} for ${url.pathname}`);
  return res.json() as Promise<T>;
}

export const getMeta = cache(() => get<Meta>("/api/meta"));

export const getPlayers = (p: { season?: string; team?: string; q?: string; sort?: string; limit?: string; rated_only?: string }) =>
  get<{ season: string; players: PlayerRow[] }>("/api/players", p);

// cache() dedupes the call between generateMetadata and the page within one request
export const getPlayer = cache((id: string, season?: string) =>
  get<PlayerDetail>(`/api/players/${encodeURIComponent(id)}`, { season }),
);

export const getTeams = (season?: string) => get<{ season: string; teams: TeamSummary[] }>("/api/teams", { season });

export const getTeam = cache((code: string, season?: string) =>
  get<{ season: string; code: string; name: string; roster: RosterRow[] }>(
    `/api/teams/${encodeURIComponent(code)}`,
    { season },
  ),
);

import "server-only";
import { notFound } from "next/navigation";
import { cache } from "react";
import type { FixturesOverview, MatchReport, StandingRow, TeamStyle } from "./match";
import type { Meta, PlayerDetail, PlayerRow, RosterRow, TeamSummary } from "./types";

const API_URL = process.env.API_URL ?? "http://127.0.0.1:8000";
const API_HEADERS = process.env.BK_API_KEY ? { "x-bk-key": process.env.BK_API_KEY } : undefined;

async function get<T>(path: string, params: Record<string, string | undefined> = {}): Promise<T> {
  const url = new URL(path, API_URL);
  for (const [k, v] of Object.entries(params)) if (v) url.searchParams.set(k, v);
  const res = await fetch(url, { headers: API_HEADERS });
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

/** A team without style data (no games in that season yet) still has a page. */
export async function getTeamStyle(code: string, season?: string): Promise<TeamStyle | null> {
  const url = new URL(`/api/teams/${encodeURIComponent(code)}/style`, API_URL);
  if (season) url.searchParams.set("season", season);
  const res = await fetch(url, { headers: API_HEADERS });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`API ${res.status} for ${url.pathname}`);
  return res.json() as Promise<TeamStyle>;
}

export const getStandings = cache((season?: string) => get<{ season: string; table: StandingRow[] }>("/api/standings", { season }));

export const getFixtures = cache(() => get<FixturesOverview>("/api/match/fixtures"));

export const getFixture = cache((id: string) => get<MatchReport>(`/api/match/fixtures/${encodeURIComponent(id)}`));

export const getTeams = (season?: string) => get<{ season: string; teams: TeamSummary[] }>("/api/teams", { season });

export const getTeam = cache((code: string, season?: string) =>
  get<{ season: string; code: string; name: string; roster: RosterRow[] }>(
    `/api/teams/${encodeURIComponent(code)}`,
    { season },
  ),
);

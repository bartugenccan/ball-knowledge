export type Group = "hucum" | "savunma" | "zihinsel";
export type Source = "veri" | "turetilmis" | "tahmini";

export interface AttributeMeta {
  key: string;
  label: string;
  group: Group;
  source: Source;
  description: string;
  display: "number" | "tier";
  hint?: AttributeHint;
}

export interface AttributeHint {
  what: string;
  how: string;
  note?: string;
}

export interface Meta {
  seasons: string[];
  latest: string;
  league_ppp: Record<string, number>;
  attributes: AttributeMeta[];
  sim_params: Record<string, unknown> & { calibrated_keys: string[] };
}

export interface Rating {
  key: string;
  value: number;
  conf: number;
  /** 80% interval on the rating scale. */
  lo?: number;
  hi?: number;
  low_data?: boolean;
  /** What the card shows: the number, a tier ("Orta") or a statement ("Üçlük kullanmıyor"). */
  display?: string;
}

export type PlayerRow = {
  player_id: string;
  player: string;
  team: string;
  team_name: string;
  games: number;
  minutes: number;
  mpg: number;
  labels: Record<string, string>;
} & Record<string, number | string | Record<string, string>>;

export interface GameLine {
  gamecode: number;
  date: string;
  round: number | null;
  team: string;
  opponent: string;
  is_home: boolean;
  minutes: number;
  pts: number;
  orb: number;
  drb: number;
  ast: number;
  stl: number;
  blk: number;
  tov: number;
  pir: number;
  plus_minus: number;
  gmsc: number;
  game_rating: number;
  short_game: boolean;
  home_score: number | null;
  away_score: number | null;
}

export interface Shot {
  x: number;
  y: number;
  made: boolean;
  zone: string;
  value: number;
  assisted: boolean;
}

export interface PlayerDetail {
  season: string;
  seasons: string[];
  player: {
    player_id: string;
    name: string;
    team: string;
    team_name: string;
    games: number;
    minutes: number;
    mpg: number;
    qualified: boolean;
  };
  ratings: Rating[];
  per_game: Record<string, number>;
  shooting: Record<string, number>;
  info: {
    clutch: { points: number; plays: number; per_play: number | null };
    corner3_attempts: number;
    inside_on_off: { fga_on: number | null; fga_off: number | null; pct_on: number | null; pct_off: number | null };
  };
  months: { month: string; games: number; ratings: Rating[] }[];
  games: GameLine[];
  shots: Shot[];
}

export interface TeamSummary {
  code: string;
  name: string;
  avg: Record<string, number>;
}

export type RosterRow = {
  player_id: string;
  player: string;
  games: number;
  minutes: number;
  mpg: number;
  qualified: boolean;
  labels: Record<string, string>;
} & Record<string, number | string | boolean | Record<string, string>>;

export interface SetOption {
  to: string;
  weight?: number;
  label?: string;
  edge?: { off: [string, string]; def: [string, string] };
}

export interface SetNode {
  type: "action" | "shot";
  label?: string;
  kind?: string;
  ball?: string;
  options?: SetOption[];
  shooter?: string;
  zone?: string;
  creation?: "catch" | "dribble";
  openness?: number;
  defender?: string;
  help?: string;
}

export interface SetDef {
  id: string;
  name: string;
  description?: string;
  start: string;
  nodes: Record<string, SetNode>;
}

export interface SimResult {
  name: string;
  iterations: number;
  ppp: number;
  points_distribution: Record<string, number>;
  turnover_rate: number;
  events: Record<string, number>;
  top_paths: { path: string; share: number }[];
  shots: Record<
    string,
    {
      label: string;
      shooter: string;
      zone: string;
      reach_rate: number;
      p_contest: number;
      p_make_open: number;
      p_make_contested: number;
      p_foul: number;
      expected_fg: number;
      ppp_when_reached: number | null;
    }
  >;
  actions: Record<string, { label: string; turnover_prob: number; options: { to: string; prob: number }[] }>;
  sensitivity?: { slot: string; player: string; ppp_contribution: number }[];
  params: { calibrated: string[] };
}

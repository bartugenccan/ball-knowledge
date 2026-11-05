// Types for team style and match simulation, as the engine writes them.

export type StandingRow = {
  rank: number; code: string; name: string; games: number; wins: number; losses: number; scored: number; allowed: number; diff: number;
  home: string; away: string; last5: boolean[]; streak: string; zone: "playoff" | "playin" | null;
};

export type Band = { mean: number; lo: number; mid: number; hi: number };

export type StyleCarrier = { name: string; rating: number; attribute: string; shown: string };
export type StyleMetric = {
  key: string; label: string; group: string; value: number; unit: string; digits: number; league: number; z: number;
  rank: number; teams: number; low: number; high: number; stable: boolean; stability: number | null; hint: string;
  carriers: StyleCarrier[];
};
export type RotationRow = { player_id: string; name: string; mpg: number; games: number; starts: number; of_games: number; curve: number[] };
export type TeamStyle = {
  season: string; code: string; name: string; games: number; early: boolean; groups: Record<string, string>;
  summary: string[]; metrics: StyleMetric[];
  efficiency: { off: number; def: number; net: number; net_rank: number; teams: number };
  rotation: RotationRow[];
  assist_pairs: { from: string; to: string; count: number; points: number }[];
  similar: { code: string; name: string }[];
};

export type GameEvent = {
  event: string; period: number; clock: string; elapsed: number; team: string | null; home: number; away: number; text: string;
  note?: string; value?: number; zone?: string; player_id?: string; coord?: [number, number]; p_make?: number;
  starters?: Record<string, string[]>;
};
export type Moment = { period: number; clock: string; elapsed: number; kind: string; text: string };
export type PeriodSummary = {
  period: number; label: string; home_points: number; away_points: number; home: number; away: number;
  top: { team: string; name: string; points: number }[]; threes: Record<string, string>; turnovers: Record<string, number>;
  runs: { team: string; points: number }[];
};
export type StoryPart = { title: string; text: string };
export type PreviewRow = { key: string; team: string | null; points: number; text: string };
export type CoachNote = { team: string; items: string[] };
export type BoxRow = { player_id: string; name: string; min: number; pts: number; reb: number; ast: number; stl: number; blk: number; tov: number; pf: number; f2: string; f3: string; ft: string };
export type Scenario = {
  index: number; home: number; away: number; quarters: number[][]; margins: number[]; lead_changes: number; ties: number;
  max_lead: number[]; best_run: number[]; overtime: boolean; box: BoxRow[][]; events: GameEvent[]; moments: Moment[]; periods: PeriodSummary[]; story: StoryPart[];
};
export type PlayerLine = {
  player_id: string; name: string; short: string; starter: boolean; position: string; usual_minutes: number;
  ratings: Record<string, number>; labels: Record<string, string>; low_data: string[];
  sim: Record<string, Band>; actual?: Record<string, number>; in_range?: Record<string, boolean>;
};
export type Leader = { name: string; rating: number; label: string | null; attribute: string };
export type Edge = { key: string; label: string; home: number; away: number; unit: string; points: number; leaders: Record<string, Leader[]> };
export type CompareRow = { stat: string; team?: string; real: number; mean: number; lo: number; mid: number; hi: number; in_range: boolean; percentile?: number };
export type Gap = { team: string; kind: string; points: number; expected: number; real: number };
export type Comparison = {
  home: number; away: number; quarters: number[][]; overtime: boolean; favored_won: boolean; margin_in_range: boolean;
  total_in_range: boolean; margins: number[]; minutes_in_band: number; table: CompareRow[]; flow: CompareRow[]; gaps: Gap[];
  subs: number[]; missing_players: number;
};
export type MatchReport = {
  id: string; season: string; gamecode?: number; round?: number; neutral: boolean;
  home: { code: string; name: string }; away: { code: string; name: string };
  sims: number; home_win: number; overtime_share: number;
  score: { home: Band; away: Band; margin: Band; total: Band };
  minute_band: { lo: number[]; mid: number[]; hi: number[] };
  quarters: { home: number[]; away: number[] };
  flow: Record<string, Band>; teams: Record<string, Record<string, Band>>; players: Record<string, PlayerLine[]>;
  edges: Edge[];
  other_side: { team?: string; share: number; rows: { label: string; upset: number; usual: number; kind: string }[] };
  typical: Scenario; other: Scenario;
  comparison?: Comparison;
  ranks?: Record<string, RankInfo | null>; tip_off?: string | null; written_at?: string;
  preview: PreviewRow[]; tempo: string; coach?: CoachNote[];
  real?: { events: GameEvent[]; moments: Moment[]; periods: PeriodSummary[]; story: StoryPart[] };
};
export type RankInfo = { rank: number; wins: number; losses: number };
export type FixtureCard = {
  id: string; round: number; tip_off: string | null; home: { code: string; name: string }; away: { code: string; name: string };
  ranks: Record<string, RankInfo | null>; written_at: string; typical: number[]; tempo: string; headline: string; status: "upcoming" | "played";
  expected: { home: number; away: number; margin_lo: number; margin_hi: number };
  real?: number[]; margin_in_range?: boolean; favored_won?: boolean;
};
export type LookBack = { games: number; winner: number; margin_error: number; margin_in_range: number; total_in_range: number; log_loss: number; net_rating_loss: number };
export type FixturesOverview = {
  season: string; updated_at: string; games: FixtureCard[];
  record: { games: number; winner?: number; margin_error?: number; margin_in_range?: number; total_in_range?: number; log_loss?: number };
  history: { known?: LookBack; likely?: LookBack };
};

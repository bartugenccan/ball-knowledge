// Publishes the site to two free Vercel projects: node scripts/deploy.mjs api|web|all [--bundle-only]
// The data never goes through GitHub: the API bundle is built here and uploaded by the CLI.
import { spawnSync } from "node:child_process";
import { cpSync, existsSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const BUNDLE = join(ROOT, ".deploy", "api");
const WEB = join(ROOT, "web");
const VERCEL = "vercel@65.11.0";
const REGION = "fra1";

// what the API reads while serving; the raw feed (195 MB) and the audit reports stay home
const TABLES = [
  "ratings_season.parquet", "ratings_month.parquet", "game_ratings.parquet", "shots.parquet", "games.parquet",
  "player_metrics.parquet", "possessions.parquet", "events.parquet",
  "team_style.json", "sim_calibration.json", "match_fixtures.json", "match_fixtures",
];
// in the lockfile for ingest and local serving, not needed by the deployed function
const NOT_SERVED = ["duckdb", "httpx", "httpcore", "certifi", "uvicorn", "click", "colorama", "h11", "httptools", "python-dotenv", "pyyaml", "uvloop", "watchfiles", "websockets"];

const ENTRY = `import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("BK_DATA_DIR", str(ROOT / "data"))

from bk.api.app import app  # noqa: E402,F401
`;

function run(command, args, cwd, capture = false) {
  const r = spawnSync(command, args, { cwd, shell: true, stdio: capture ? ["ignore", "pipe", "inherit"] : "inherit", encoding: "utf8" });
  if (r.status !== 0) {
    console.error(`\nFailed: ${command} ${args.join(" ")}`);
    process.exit(r.status ?? 1);
  }
  return r.stdout;
}

function bundleApi() {
  for (const part of ["bk", "index.py", "data", "requirements.txt", "vercel.json", ".python-version"]) rmSync(join(BUNDLE, part), { recursive: true, force: true });
  mkdirSync(join(BUNDLE, "data", "tables"), { recursive: true });
  cpSync(join(ROOT, "engine", "bk"), join(BUNDLE, "bk"), { recursive: true, filter: (src) => !src.includes("__pycache__") });
  for (const name of TABLES) {
    const from = join(ROOT, "data", "tables", name);
    if (!existsSync(from)) {
      console.error(`Missing table: ${name}. Build the tables first (README).`);
      process.exit(1);
    }
    cpSync(from, join(BUNDLE, "data", "tables", name), { recursive: true });
  }
  writeFileSync(join(BUNDLE, "index.py"), ENTRY);
  writeFileSync(join(BUNDLE, ".python-version"), "3.13\n");
  // vercel link leaves a token in .env.local; it must never be uploaded
  writeFileSync(join(BUNDLE, ".vercelignore"), ".env*\n");
  const skip = NOT_SERVED.flatMap((p) => ["--no-emit-package", p]);
  writeFileSync(join(BUNDLE, "requirements.txt"), run("uv", ["export", "--directory", "engine", "--frozen", "--no-dev", "--no-hashes", "--no-emit-project", "--quiet", ...skip], ROOT, true));
  writeFileSync(join(BUNDLE, "vercel.json"), `${JSON.stringify({
    regions: [REGION],
    git: { deploymentEnabled: false },
    functions: { "index.py": { includeFiles: "{bk,data}/**", maxDuration: 60 } },
  }, null, 2)}\n`);
  console.log(`API bundle ready: ${BUNDLE}`);
}

function publish(dir, project) {
  if (!existsSync(join(dir, ".vercel", "project.json"))) {
    run("npx", ["--yes", VERCEL, "link", "--yes", "--project", project], dir);
    // link --yes connects the GitHub repo; publishing stays a deliberate command, a push must not touch the live site
    run("npx", ["--yes", VERCEL, "git", "disconnect", "--yes"], dir);
  }
  run("npx", ["--yes", VERCEL, "deploy", "--prod", "--yes"], dir);
}

const [target, flag] = process.argv.slice(2);
if (!["api", "web", "all"].includes(target)) {
  console.error("usage: node scripts/deploy.mjs api|web|all [--bundle-only]");
  process.exit(1);
}
if (target !== "web") {
  bundleApi();
  if (flag !== "--bundle-only") publish(BUNDLE, "ball-knowledge-api");
}
if (target !== "api" && flag !== "--bundle-only") publish(WEB, "ball-knowledge-web");

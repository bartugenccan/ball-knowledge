// Runs before `npm run dev`: installs whatever is missing or stale, then checks the data.
// Uses only Node built-ins so it works on a fresh clone.
import { spawnSync } from "node:child_process";
import { existsSync, statSync } from "node:fs";

const fail = (lines) => {
  console.error(`\n${lines.join("\n")}\n`);
  process.exit(1);
};

const run = (cmd, label) => {
  console.log(`\n> ${label}: ${cmd}`);
  const r = spawnSync(cmd, { stdio: "inherit", shell: true });
  if (r.status !== 0) fail([`Komut başarısız oldu: ${cmd}`]);
};

// node_modules is stale when the lockfile changed after the last install (e.g. after a git pull)
const needsInstall = (dir) => {
  const marker = `${dir}/node_modules/.package-lock.json`;
  if (!existsSync(marker)) return true;
  const lock = `${dir}/package-lock.json`;
  return existsSync(lock) && statSync(lock).mtimeMs > statSync(marker).mtimeMs;
};

// 1. uv: `uv run` creates/syncs engine/.venv by itself (and fetches Python 3.13 if needed)
if (spawnSync("uv --version", { shell: true, stdio: "ignore" }).status !== 0) {
  fail([
    "uv bulunamadı. Python tarafı için gerekli.",
    "Kurulum: https://docs.astral.sh/uv/getting-started/installation/",
    "  Windows: powershell -c \"irm https://astral.sh/uv/install.ps1 | iex\"",
    "  macOS/Linux: curl -LsSf https://astral.sh/uv/install.sh | sh",
    "Kurduktan sonra terminali kapatıp açın ve tekrar `npm run dev` çalıştırın.",
  ]);
}

// 2. JS dependencies
if (needsInstall(".")) run("npm install", "Kök bağımlılıklar");
if (needsInstall("web")) run("npm --prefix web install", "Web bağımlılıkları");
if (!existsSync("engine/.venv")) run("uv --directory engine sync", "Python ortamı");

// 3. data
const required = ["data/tables/ratings_season.parquet", "data/tables/sim_calibration.json"];
const missing = required.filter((p) => !existsSync(p));
if (missing.length) {
  fail([
    `Eksik dosya: ${missing.join(", ")}`,
    "Paylaşılan 'tables' klasörünü repo köküne data/tables olarak koyun",
    "ya da veriyi baştan üretin (README > Veriyi baştan üretmek).",
  ]);
}

console.log("\nKurulum tamam, sunucular başlıyor. Site: http://localhost:3000  API: http://127.0.0.1:8000/docs\n");

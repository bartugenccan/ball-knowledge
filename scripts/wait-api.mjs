// Hold the web server until the API answers, so the first page load doesn't hit a closed port.
const url = "http://127.0.0.1:8000/api/meta";
const deadline = Date.now() + 120_000;

while (Date.now() < deadline) {
  try {
    if ((await fetch(url)).ok) process.exit(0);
  } catch {}
  await new Promise((r) => setTimeout(r, 500));
}
console.error("API 2 dakikada açılmadı; [api] satırlarındaki hataya bakın.");
process.exit(1);

# /// script
# requires-python = ">=3.11"
# dependencies = ["anthropic>=1,<2"]
# ///
"""Can a vision model turn a coach's clips into usable set notes? A small, blind test.

    uv run scout.py run --split dev --dry-run     # frames and estimated cost, no API call
    uv run scout.py run --split dev               # sends frames to the API, resumes if interrupted
    uv run scout.py score --split test            # scores predictions against the coach's labels

Inputs live in this folder and stay out of git: clips/, labels.csv, sets.csv, review.csv.
Clip file names are never sent to the model, so they cannot leak the answer.
"""

from __future__ import annotations

import argparse
import base64
import csv
import json
import math
import subprocess
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).parent
MODEL = "claude-opus-5-5"
USD_PER_INPUT_TOKEN, USD_PER_OUTPUT_TOKEN = 4 / 1e6, 20 / 1e6
MAX_REQUEST_BYTES = 30 * 1024 * 1024  # stay under the Messages API request size limit
UNKNOWN = "bilinmiyor"

ACTIONS = ["pick_and_roll", "handoff", "off_ball_screen", "post_up", "isolation", "cut", "transition", "other"]
ZONES = ["rim", "paint", "mid", "corner3", "above_break3", "none"]
RESULTS = ["made", "missed", "turnover", "foul", "other"]
CONFIDENCE = ["low", "medium", "high"]

SYSTEM = """You are helping a basketball assistant coach break down an opponent's half-court possessions.
You receive frames from one possession, each labelled with its time in seconds. Frames are samples, so movement between them is unseen.

Report only what the frames support. Screens are brief and players may leave the camera's view, so state when something could not be seen rather than inferring it. Read a jersey number only when it is legible. Choosing "bilinmiyor" or low confidence is a correct and useful answer when the evidence is thin: a coach loses more from one confident wrong call than from an honest "not sure".

Write descriptions in Turkish, using the basketball terms coaches normally use."""


@dataclass(frozen=True)
class Label:
    clip_id: str
    file: str
    split: str
    set_name: str
    primary_action: str
    shot_zone: str
    result: str
    finisher_jersey: str


def norm(value: str) -> str:
    return (value or "").strip().casefold()


def read_csv(path: Path) -> list[dict[str, str]]:
    """Read a CSV saved by Excel: tolerates a BOM and the semicolons Turkish locales use."""
    text = path.read_text(encoding="utf-8-sig")
    delimiter = ";" if text.splitlines()[0].count(";") > text.splitlines()[0].count(",") else ","
    return [{k.strip(): (v or "").strip() for k, v in row.items() if k} for row in csv.DictReader(text.splitlines(), delimiter=delimiter)]


def load_sets(path: Path) -> dict[str, str]:
    return {row["set_name"]: row.get("description", "") for row in read_csv(path)}


def load_labels(path: Path, sets: dict[str, str]) -> list[Label]:
    """Parse labels and fail on the first bad value, so a typo cannot quietly count as a miss."""
    allowed_sets = {norm(s) for s in sets} | {UNKNOWN}
    labels, seen = [], set()
    for line, row in enumerate(read_csv(path), start=2):
        label = Label(row["clip_id"], row["file"], norm(row["split"]), norm(row["set_name"]),
                      norm(row["primary_action"]), norm(row["shot_zone"]), norm(row["result"]),
                      norm(row.get("finisher_jersey", "")))
        checks = [("split", label.split, {"dev", "test"}), ("set_name", label.set_name, allowed_sets),
                  ("primary_action", label.primary_action, set(ACTIONS)), ("shot_zone", label.shot_zone, set(ZONES)),
                  ("result", label.result, set(RESULTS))]
        for field, value, allowed in checks:
            if value not in allowed:
                sys.exit(f"{path.name} satır {line}: {field}='{value}' geçersiz. İzin verilenler: {sorted(allowed)}")
        if label.clip_id in seen:
            sys.exit(f"{path.name} satır {line}: clip_id '{label.clip_id}' tekrar ediyor")
        seen.add(label.clip_id)
        labels.append(label)
    return labels


def schema(set_names: list[str]) -> dict:
    step = {"type": "object", "additionalProperties": False, "required": ["second", "description"],
            "properties": {"second": {"type": "number"}, "description": {"type": "string"}}}
    return {
        "type": "object", "additionalProperties": False,
        "required": ["set_name", "confidence", "primary_action", "shot_zone", "result", "finisher_jersey",
                     "steps", "not_visible"],
        "properties": {
            "set_name": {"type": "string", "enum": [*set_names, UNKNOWN]},
            "confidence": {"type": "string", "enum": CONFIDENCE},
            "primary_action": {"type": "string", "enum": ACTIONS},
            "shot_zone": {"type": "string", "enum": ZONES},
            "result": {"type": "string", "enum": RESULTS},
            "finisher_jersey": {"type": "string", "description": f"Legible jersey number, otherwise '{UNKNOWN}'"},
            "steps": {"type": "array", "items": step, "description": "The possession in order, each step tied to a frame time"},
            "not_visible": {"type": "string", "description": "What could not be seen or judged from these frames"},
        },
    }


def extract_frames(clip: Path, fps: float, long_edge: int, out_dir: Path) -> list[Path]:
    scale = f"scale='if(gte(iw,ih),min({long_edge},iw),-2)':'if(gte(iw,ih),-2,min({long_edge},ih))'"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(clip), "-vf", f"fps={fps},{scale}", "-q:v", "3",
                    str(out_dir / "%05d.jpg")], check=True)
    return sorted(out_dir.glob("*.jpg"))


def frame_size(frame: Path) -> tuple[int, int]:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v", "-show_entries", "stream=width,height",
                          "-of", "csv=p=0", str(frame)], check=True, capture_output=True, text=True).stdout
    width, height = out.strip().split(",")[:2]
    return int(width), int(height)


def estimate_usd(frames: list[Path]) -> float:
    """Input cost of the images, using the documented 28x28 px patch rule."""
    if not frames:
        return 0.0
    width, height = frame_size(frames[0])
    return len(frames) * math.ceil(width / 28) * math.ceil(height / 28) * USD_PER_INPUT_TOKEN


def build_content(frames: list[Path], fps: float, sets: dict[str, str]) -> list[dict]:
    content: list[dict] = []
    for i, frame in enumerate(frames):
        data = base64.standard_b64encode(frame.read_bytes()).decode("ascii")
        content.append({"type": "text", "text": f"t={i / fps:.1f}s"})
        content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": data}})
    catalog = "\n".join(f"- {name}: {desc}" for name, desc in sets.items())
    content.append({"type": "text", "text": f"The coach's set list:\n{catalog}\n\nBreak down this possession. "
                                            f"Use '{UNKNOWN}' for the set if it does not match the list or you cannot tell."})
    return content


def request_bytes(content: list[dict]) -> int:
    return sum(len(block.get("source", {}).get("data", "")) + len(block.get("text", "")) for block in content)


def call_model(client, content: list[dict], output_schema: dict) -> dict:
    with client.beta.messages.stream(
        model=MODEL, max_tokens=8000, system=SYSTEM,
        betas=["server-side-fallback-2026-07-01"], fallbacks="default",
        output_config={"effort": "high", "format": {"type": "json_schema", "schema": output_schema}},
        messages=[{"role": "user", "content": content}],
    ) as stream:
        response = stream.get_final_message()
    usage = response.usage
    usd = usage.input_tokens * USD_PER_INPUT_TOKEN + usage.output_tokens * USD_PER_OUTPUT_TOKEN
    meta = {"served_by": response.model, "input_tokens": usage.input_tokens,
            "output_tokens": usage.output_tokens, "usd": round(usd, 4)}
    if response.stop_reason != "end_turn":
        return {**meta, "error": f"stop_reason={response.stop_reason}"}
    text = next(block.text for block in response.content if block.type == "text")
    return {**meta, "prediction": json.loads(text)}


def predictions_path(run: str) -> Path:
    return HERE / "results" / run / "predictions.jsonl"


def load_predictions(path: Path) -> dict[str, dict]:
    if not path.exists():
        return {}
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return {row["clip_id"]: row for row in rows}


def cmd_run(args: argparse.Namespace) -> None:
    sets = load_sets(HERE / "sets.csv")
    labels = [lb for lb in load_labels(HERE / "labels.csv", sets) if lb.split == args.split]
    path = predictions_path(args.run)
    done = {cid for cid, row in load_predictions(path).items() if "prediction" in row}
    pending = [lb for lb in labels if lb.clip_id not in done]
    client = None
    if not args.dry_run:
        import anthropic
        client = anthropic.Anthropic()
        path.parent.mkdir(parents=True, exist_ok=True)
    spent = 0.0
    for lb in pending:
        clip = HERE / "clips" / lb.file
        if not clip.exists():
            sys.exit(f"Klip bulunamadı: {clip}")
        with tempfile.TemporaryDirectory() as tmp:
            frames = extract_frames(clip, args.fps, args.long_edge, Path(tmp))
            estimate = estimate_usd(frames)
            content = build_content(frames, args.fps, sets)
            size = request_bytes(content)
            if size > MAX_REQUEST_BYTES:
                sys.exit(f"{lb.clip_id}: istek {size / 1e6:.0f} MB, sınırın üstünde. --fps veya --long-edge değerini düşürün.")
            if args.dry_run:
                print(f"{lb.clip_id}: {len(frames)} kare, {size / 1e6:.1f} MB, görüntü girdisi ~${estimate:.2f}")
                spent += estimate
                continue
            if spent + estimate > args.max_usd:
                print(f"Bütçe sınırı ${args.max_usd:.2f}: {lb.clip_id} ve sonrası çalıştırılmadı. Tekrar çalıştırınca kaldığı yerden sürer.")
                break
            result = call_model(client, content, schema(list(sets)))
        spent += result["usd"]
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"clip_id": lb.clip_id, "fps": args.fps, "frames": len(frames), **result}, ensure_ascii=False) + "\n")
        print(f"{lb.clip_id}: {result.get('error') or result['prediction']['set_name']} (${result['usd']:.2f})")
    label = "tahmini görüntü girdisi" if args.dry_run else "harcanan"
    print(f"{len(pending)} bekleyen klip, {label}: ${spent:.2f}")


def wilson(hits: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 0.0
    p = hits / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return center - margin, center + margin


def score(labels: list[Label], predictions: dict[str, dict]) -> dict:
    """Every labelled clip counts. A failed or missing prediction scores as wrong, never as skipped."""
    answered = {lb.clip_id: predictions.get(lb.clip_id, {}).get("prediction") for lb in labels}

    def accuracy(field: str, subset: list[Label]) -> dict:
        hits = sum(1 for lb in subset if answered[lb.clip_id] and norm(answered[lb.clip_id][field]) == getattr(lb, field))
        low, high = wilson(hits, len(subset))
        return {"hits": hits, "n": len(subset), "acc": hits / len(subset) if subset else None, "ci95": [low, high]}

    named = [lb for lb in labels if lb.set_name != UNKNOWN]
    unknown = [lb for lb in labels if lb.set_name == UNKNOWN]
    confident = [lb for lb in labels if answered[lb.clip_id] and answered[lb.clip_id]["confidence"] == "high"]
    confident_wrong = sum(1 for lb in confident if norm(answered[lb.clip_id]["set_name"]) != lb.set_name)
    common = Counter(lb.set_name for lb in labels).most_common(1)
    return {
        "clips": len(labels),
        "no_answer": sum(1 for lb in labels if not answered[lb.clip_id]),
        "set": accuracy("set_name", labels),
        "set_baseline_most_common": common[0][1] / len(labels) if common else None,
        "set_on_named_clips": accuracy("set_name", named),
        "unknown_clips_rejected": accuracy("set_name", unknown),
        "primary_action": accuracy("primary_action", labels),
        "shot_zone": accuracy("shot_zone", [lb for lb in labels if lb.shot_zone != "none"]),
        "result": accuracy("result", labels),
        "finisher_jersey": accuracy("finisher_jersey", [lb for lb in labels if lb.finisher_jersey not in ("", UNKNOWN)]),
        "high_confidence": {"n": len(confident), "wrong": confident_wrong,
                            "wrong_rate": confident_wrong / len(confident) if confident else None},
    }


def score_review(rows: list[dict[str, str]]) -> dict | None:
    """Coach's stopwatch. Each clip is timed once, either from scratch or fixing the AI draft, never both."""
    if not rows:
        return None
    minutes: dict[str, list[float]] = {"scratch": [], "fix": []}
    for row in rows:
        minutes[norm(row["mode"])].append(float(row["minutes"].replace(",", ".")))
    if not minutes["scratch"] or not minutes["fix"]:
        return {"n_scratch": len(minutes["scratch"]), "n_fix": len(minutes["fix"]), "saved": None}
    scratch = sum(minutes["scratch"]) / len(minutes["scratch"])
    fix = sum(minutes["fix"]) / len(minutes["fix"])
    useful = [float(row["useful_1_5"]) for row in rows if row.get("useful_1_5")]
    return {"n_scratch": len(minutes["scratch"]), "n_fix": len(minutes["fix"]), "scratch_min": scratch, "fix_min": fix,
            "saved": 1 - fix / scratch, "useful_mean": sum(useful) / len(useful) if useful else None}


def verdicts(report: dict, review: dict | None, min_confident: int = 10) -> list[tuple[str, str]]:
    hc = report["high_confidence"]
    if hc["n"] < min_confident:
        wrong = f"YETERSİZ VERİ ({hc['n']} yüksek güvenli cevap, en az {min_confident} gerekli)"
    else:
        wrong = f"{'GEÇTİ' if hc['wrong_rate'] < 0.10 else 'KALDI'} (%{100 * hc['wrong_rate']:.0f}, hedef <%10)"
    if not review or review["saved"] is None:
        saved = "YETERSİZ VERİ (review.csv'de iki mod da gerekli)"
    else:
        saved = f"{'GEÇTİ' if review['saved'] >= 0.50 else 'KALDI'} (%{100 * review['saved']:.0f}, hedef ≥%50)"
    return [("Yüksek güvenli yanlış oranı", wrong), ("Koçun kazandığı zaman", saved)]


def print_report(report: dict, review: dict | None) -> None:
    print(f"Klip: {report['clips']}, cevapsız: {report['no_answer']}")
    names = {"set": "Set adı (tüm klipler)", "set_on_named_clips": "Set adı (listedeki setler)",
             "unknown_clips_rejected": "Listede olmayanı 'bilinmiyor' deme", "primary_action": "Ana aksiyon",
             "shot_zone": "Şut bölgesi", "result": "Sonuç", "finisher_jersey": "Bitiren forma no"}
    for key, title in names.items():
        row = report[key]
        if row["n"]:
            print(f"  {title:38s} {row['hits']}/{row['n']} = %{100 * row['acc']:.0f}  (%95 aralık %{100 * row['ci95'][0]:.0f}-%{100 * row['ci95'][1]:.0f})")
    if report["set_baseline_most_common"] is not None:
        print(f"  Hep en sık seti söyleseydi: %{100 * report['set_baseline_most_common']:.0f}")
    print("\nKararlar:")
    for name, verdict in verdicts(report, review):
        print(f"  {name}: {verdict}")


def cmd_score(args: argparse.Namespace) -> None:
    sets = load_sets(HERE / "sets.csv")
    labels = [lb for lb in load_labels(HERE / "labels.csv", sets) if lb.split == args.split]
    predictions = load_predictions(predictions_path(args.run))
    review_file = HERE / "review.csv"
    ids = {lb.clip_id for lb in labels}
    review_rows = [r for r in read_csv(review_file) if r["clip_id"] in ids] if review_file.exists() else []
    print_report(score(labels, predictions), score_review(review_rows))


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run")
    run.add_argument("--split", choices=["dev", "test"], default="dev")
    run.add_argument("--run", default="baseline", help="results/<run>/ altına yazar; prompt veya ayar değişince yeni ad verin")
    run.add_argument("--fps", type=float, default=2.0)
    run.add_argument("--long-edge", type=int, default=1280)
    run.add_argument("--max-usd", type=float, default=5.0)
    run.add_argument("--dry-run", action="store_true")
    run.set_defaults(func=cmd_run)
    scorer = sub.add_parser("score")
    scorer.add_argument("--split", choices=["dev", "test"], default="dev")
    scorer.add_argument("--run", default="baseline")
    scorer.set_defaults(func=cmd_score)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

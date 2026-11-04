"""uv run --with pytest --with "anthropic>=1,<2" pytest test_scout.py"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

import scout

SETS = {"Horns Flare": "", "Spain PnR": ""}


def label(cid, set_name="horns flare", action="pick_and_roll", zone="rim", result="made", jersey="7"):
    return scout.Label(cid, f"{cid}.mp4", "test", set_name, action, zone, result, jersey)


def prediction(set_name="Horns Flare", confidence="high", action="pick_and_roll", zone="rim", result="made", jersey="7"):
    return {"prediction": {"set_name": set_name, "confidence": confidence, "primary_action": action, "shot_zone": zone,
                           "result": result, "finisher_jersey": jersey, "steps": [], "not_visible": ""}}


def test_missing_and_failed_predictions_count_as_wrong():
    labels = [label("a"), label("b"), label("c")]
    report = scout.score(labels, {"a": prediction(), "b": {"error": "stop_reason=refusal"}})
    assert report["no_answer"] == 2
    assert report["set"]["hits"] == 1 and report["set"]["n"] == 3


def test_saying_unknown_on_an_unlisted_set_is_correct_and_is_measured_separately():
    labels = [label("a", set_name=scout.UNKNOWN), label("b", set_name=scout.UNKNOWN)]
    report = scout.score(labels, {"a": prediction(set_name=scout.UNKNOWN), "b": prediction()})
    assert report["unknown_clips_rejected"]["hits"] == 1
    assert report["set_on_named_clips"]["n"] == 0


def test_high_confidence_wrong_rate_ignores_lower_confidence_answers():
    labels = [label("a"), label("b"), label("c")]
    predictions = {"a": prediction(), "b": prediction(set_name="Spain PnR"), "c": prediction(set_name="Spain PnR", confidence="low")}
    hc = scout.score(labels, predictions)["high_confidence"]
    assert (hc["n"], hc["wrong"], hc["wrong_rate"]) == (2, 1, 0.5)


def test_time_gate_needs_both_modes_and_turkish_decimals_parse():
    assert scout.score_review([{"mode": "fix", "minutes": "2"}])["saved"] is None
    review = scout.score_review([{"mode": "scratch", "minutes": "4,0", "useful_1_5": ""},
                                 {"mode": "fix", "minutes": "1,0", "useful_1_5": "4"}])
    assert review["saved"] == 0.75 and review["useful_mean"] == 4


def test_verdicts_refuse_to_pass_on_too_few_confident_answers():
    report = scout.score([label("a")], {"a": prediction()})
    assert "YETERSİZ" in scout.verdicts(report, None)[0][1]
    assert "YETERSİZ" in scout.verdicts(report, None)[1][1]


def test_excel_semicolon_csv_with_bom_loads(tmp_path):
    path = tmp_path / "labels.csv"
    path.write_bytes("﻿clip_id;file;split;set_name;primary_action;shot_zone;result;finisher_jersey\n"
                     "1;a.mp4;test;Horns Flare;pick_and_roll;rim;made;7\n".encode("utf-8"))
    assert scout.load_labels(path, SETS)[0].set_name == "horns flare"


def test_a_label_typo_stops_the_run_instead_of_counting_as_a_miss(tmp_path):
    path = tmp_path / "labels.csv"
    path.write_text("clip_id,file,split,set_name,primary_action,shot_zone,result,finisher_jersey\n"
                    "1,a.mp4,test,Hornz,pick_and_roll,rim,made,7\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="set_name"):
        scout.load_labels(path, SETS)


def test_schema_limits_set_answers_to_the_coach_list_plus_unknown():
    assert scout.schema(list(SETS))["properties"]["set_name"]["enum"] == ["Horns Flare", "Spain PnR", scout.UNKNOWN]


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg yok")
def test_frames_are_timed_downscaled_and_the_file_name_never_reaches_the_model(tmp_path):
    clip = tmp_path / "horns_flare_cevap.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "testsrc=size=1920x1080:rate=30:duration=3",
                    "-pix_fmt", "yuv420p", str(clip)], check=True)
    out = tmp_path / "frames"
    out.mkdir()
    frames = scout.extract_frames(clip, 2.0, 1280, out)
    assert len(frames) == 6
    assert scout.frame_size(frames[0]) == (1280, 720)
    content = scout.build_content(frames, 2.0, SETS)
    sent_text = json.dumps([b for b in content if b["type"] == "text"])
    assert "t=2.5s" in sent_text and "horns_flare_cevap" not in sent_text
    assert scout.estimate_usd(frames) == pytest.approx(6 * 46 * 26 * 4 / 1e6)


def test_sdk_accepts_the_arguments_this_script_sends():
    import inspect

    import anthropic

    params = inspect.signature(anthropic.Anthropic(api_key="x").beta.messages.stream).parameters
    assert {"betas", "fallbacks", "output_config", "system"} <= set(params)

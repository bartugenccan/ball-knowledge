import re

from bk.match.story import club, coach_notes, game_story, pick, preview, quarter_story, tempo_line

FORBIDDEN = ("perde", "pick", "izole", "savundu", "boş şut", "kontes", "set ")
SUFFIXED_NAME = re.compile(r"(Fenerbahçe|Real Madrid|Baskonia|Tavares|Hezonja)'[a-zçğıöşü]")


def period(n=1, home=20, away=12, top=None, threes=None, turnovers=None, runs=None, h=20, a=12):
    return {"period": n, "label": f"{n}. çeyrek", "home_points": h, "away_points": a, "home": home, "away": away,
            "top": top or [], "threes": threes or {"ULK": "2/6", "MAD": "2/6"}, "turnovers": turnovers or {"ULK": 2, "MAD": 2}, "runs": runs or []}


def edge(key, points, home, away, unit="", leaders=None):
    return {"key": key, "label": key, "home": home, "away": away, "unit": unit, "points": points, "leaders": leaders or {"ULK": [], "MAD": []}}


def report(edges, f3a=(26, 26), inside=(30, 30), poss=73.0, total=170.0):
    def team(three, paint):
        return {"f3a": {"mean": three}, "inside_a": {"mean": paint}, "poss": {"mean": poss}}
    return {"home": {"code": "ULK"}, "away": {"code": "MAD"}, "edges": edges, "teams": {"ULK": team(f3a[0], inside[0]), "MAD": team(f3a[1], inside[1])}, "score": {"total": {"mean": total}}}


def test_same_facts_always_read_the_same_and_options_vary():
    assert pick("a", ["x", "y", "z"]) == pick("a", ["x", "y", "z"])
    assert len({pick(str(i), ["x", "y", "z"]) for i in range(30)}) == 3


def test_quarter_names_the_winner_the_scorer_and_a_hot_hand():
    p = period(top=[{"team": "ULK", "name": "Baldwin", "points": 11}], threes={"ULK": "4/6", "MAD": "1/6"}, runs=[{"team": "ULK", "points": 12}], turnovers={"ULK": 1, "MAD": 6})
    text = quarter_story(p, (0, 0), [], "ULK", "MAD")
    for needle in ("Fenerbahçe", "Baldwin", "11", "4/6", "1/6", "12-0", "6 top kaybı"):
        assert needle in text, needle


def test_quiet_details_stay_out():
    text = quarter_story(period(h=20, a=19, home=20, away=19, threes={"ULK": "1/3", "MAD": "2/6"}), (0, 0), [], "ULK", "MAD")
    assert "üçlükte" not in text and "top kaybı" not in text


def test_lead_change_is_called_only_when_it_happens():
    change = quarter_story(period(n=2, home=40, away=38), (30, 33), [], "ULK", "MAD")
    keep = quarter_story(period(n=2, home=40, away=38), (33, 30), [], "ULK", "MAD")
    assert "el değiştirdi" in change and "el değiştirdi" not in keep


def test_no_invented_basketball_and_no_endings_on_names():
    p = period(top=[{"team": "ULK", "name": "Tavares", "points": 9}], threes={"ULK": "4/6", "MAD": "1/6"})
    text = quarter_story(p, (0, 0), [], "ULK", "MAD") + " ".join(r["text"] for r in preview(report([edge("rebounds", 3.0, 33, 27, "%"), edge("shooting", 2.0, 55, 52, "%")])))
    assert not any(w in text.lower() for w in FORBIDDEN)
    assert not SUFFIXED_NAME.search(text)


def test_game_story_ends_on_the_final_score():
    p = period(home=88, away=80, h=20, a=20)
    out = game_story([], [p], [], "ULK", "MAD")
    assert out[-1]["title"] == "Son düdük" and "88-80" in out[-1]["text"] and club("ULK") in out[-1]["text"]


def test_preview_leaves_out_small_edges_and_orders_by_size():
    rows = preview(report([edge("turnovers", 0.5, 11, 12), edge("shooting", 1.5, 55, 53, "%"), edge("free_throws", 3.0, 18, 15)]))
    assert [r["key"] for r in rows] == ["free_throws", "shooting"]


def test_rebounds_claim_says_it_does_not_win_games_alone():
    assert "tek başına" in preview(report([edge("rebounds", 2.0, 33, 27, "%")]))[0]["text"]


def test_no_clear_edge_says_so():
    assert preview(report([edge("shooting", 0.2, 54, 54, "%")]))[0]["key"] == "even"


def test_shot_style_is_character_not_an_edge():
    rows = preview(report([edge("shooting", 2.0, 55, 52, "%")], f3a=(31, 25)))
    style = [r for r in rows if r["key"] == "style"]
    assert style and style[0]["points"] == 0.0 and style[0]["team"] == "ULK"


def test_paint_gap_is_not_told_it_came_true_too_rarely():
    rows = preview(report([edge("shooting", 2.0, 55, 52, "%")], inside=(36, 28)))
    assert not [r for r in rows if r["key"] == "style"]


def test_rebound_claim_is_hedged_it_came_true_under_65_percent():
    for points in (1.3, 2.0, 3.0, 4.0, 5.0, 6.0):
        text = preview(report([edge("rebounds", points, 33 + points, 27, "%")]))[0]["text"]
        assert "biraz" in text


def test_tempo_line_follows_possessions():
    assert "yüksek" in tempo_line(report([], poss=76.0))
    assert "Yavaş" in tempo_line(report([], poss=71.0))


def test_coach_notes_only_use_differences_that_are_real():
    rows = [{"team": "ULK", "label": "Top kaybını %15 azaltmak", "margin": 2.4, "significant": True}, {"team": "ULK", "label": "Hücum ribaundunu %15 artırmak", "margin": 0.3, "significant": False}]
    notes = coach_notes({"home": {"code": "ULK"}, "away": {"code": "MAD"}}, rows)
    assert len(notes[0]["items"]) == 1 and "2.4" in notes[0]["items"][0]
    assert "öne çıkmıyor" in notes[1]["items"][0]

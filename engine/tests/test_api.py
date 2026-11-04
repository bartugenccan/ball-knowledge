import pytest

from bk.config import TABLES_DIR

pytestmark = pytest.mark.skipif(not (TABLES_DIR / "ratings_season.parquet").exists(),
                                reason="tables not built (run ingest, model.build, ratings.build)")


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    from bk.api.app import app
    return TestClient(app)


def test_meta_and_players(client):
    meta = client.get("/api/meta").json()
    assert len(meta["attributes"]) == 18
    assert {a["key"]: a["display"] for a in meta["attributes"]}["mid_range"] == "tier"
    assert not {"clutch", "corner_three"} & {a["key"] for a in meta["attributes"]}
    assert all(a["hint"]["what"] and a["hint"]["how"] for a in meta["attributes"])
    ps = client.get("/api/players", params={"limit": 5}).json()["players"]
    assert len(ps) == 5 and all(1 <= p["three_point"] <= 20 for p in ps)


def test_player_detail(client):
    pid = client.get("/api/players", params={"limit": 1}).json()["players"][0]["player_id"]
    d = client.get(f"/api/players/{pid}").json()
    assert d["player"]["player_id"] == pid
    assert len(d["ratings"]) == 18 and d["games"] and d["shots"]
    rating = d["ratings"][0]
    assert rating["lo"] <= rating["value"] <= rating["hi"]
    assert {"low_data", "display", "conf"} <= set(rating)
    assert set(d["shooting"]) == {"inside", "mid", "corner3", "three", "ft"}
    assert "clutch" in d["info"] and "inside_on_off" in d["info"]


def test_simulate_team_set(client):
    team = client.get("/api/teams").json()["teams"][0]["code"]
    roster = client.get(f"/api/teams/{team}").json()["roster"][:10]
    off = {str(i + 1): roster[i]["player_id"] for i in range(5)}
    dfn = {str(i + 1): roster[i + 5]["player_id"] for i in range(5)}
    s = client.get("/api/sets").json()["sets"][0]
    r = client.post("/api/simulate", json={"set": s, "offense": off, "defense": dfn, "iterations": 1000}).json()
    assert 0.5 < r["ppp"] < 1.8 and len(r["sensitivity"]) == 5


def test_simulate_rejects_missing_slots(client):
    s = client.get("/api/sets").json()["sets"][0]
    r = client.post("/api/simulate", json={"set": s, "offense": {"1": "x"}, "defense": {"1": "y"}})
    assert r.status_code == 400


def test_non_numeric_attributes_show_their_label(client):
    ps = client.get("/api/players", params={"limit": 400}).json()["players"]
    assert all(p["labels"]["mid_range"] in {"Düşük", "Orta", "Yüksek", "Orta mesafe kullanmıyor"} for p in ps)
    assert any(p["labels"]["mid_range"] == "Orta mesafe kullanmıyor" for p in ps)
    assert all(p["labels"]["perimeter_defense"] in {"Düşük", "Orta", "Yüksek"} for p in ps)
    assert all(str(p["three_point"]) != p["labels"].get("three_point") for p in ps)


def test_leader_lists_leave_out_low_data_and_non_shooters(client):
    everyone = client.get("/api/players", params={"sort": "three_point", "limit": 400}).json()["players"]
    leaders = client.get("/api/players", params={"sort": "three_point", "rated_only": True, "limit": 400}).json()["players"]
    assert 0 < len(leaders) < len(everyone)
    assert all("three_point" not in p["labels"] for p in leaders)


def test_leader_lists_leave_out_very_small_roles_but_ratings_stay(client):
    everyone = client.get("/api/players", params={"sort": "steals", "limit": 400, "season": "E2025"}).json()["players"]
    leaders = client.get("/api/players", params={"sort": "steals", "rated_only": True, "limit": 400, "season": "E2025"}).json()["players"]
    assert all(p["mpg"] >= 10 for p in leaders)
    small_role = [p for p in everyone if p["mpg"] < 10]
    assert small_role and all(1 <= p["steals"] <= 20 for p in small_role)

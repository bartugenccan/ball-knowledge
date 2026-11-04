from bk.ingest.client import EuroleagueClient


def test_cached_game_file_is_not_refetched(tmp_path):
    calls = []

    with EuroleagueClient(raw_dir=tmp_path, min_interval=0) as c:
        c._get_json = lambda url, params=None: calls.append(url) or {"Rows": [1]}
        first, fetched1 = c.game_file("E2099", 1, "Points")
        second, fetched2 = c.game_file("E2099", 1, "Points")
    assert first == second == {"Rows": [1]}
    assert (fetched1, fetched2) == (True, False)
    assert len(calls) == 1


def test_season_reference_files_keep_last_good_copy(tmp_path):
    replies = [{"data": [1]}, None]
    with EuroleagueClient(raw_dir=tmp_path, min_interval=0) as c:
        c._get_json = lambda url, params=None: replies.pop(0)
        assert c.people("E2099") == {"data": [1]}
        assert c.people("E2099") == {"data": [1]}  # empty answer must not erase the cached file
        assert c.people("E2099", refresh=False) == {"data": [1]}  # no third request
    assert replies == []


def test_official_totals_ask_for_accumulated_numbers(tmp_path):
    seen = {}

    def fake(url, params=None):
        seen.update(params)
        return {"players": []}

    with EuroleagueClient(raw_dir=tmp_path, min_interval=0) as c:
        c._get_json = fake
        c.official_player_totals("E2099")
    assert seen["statisticMode"] == "accumulated" and seen["SeasonCode"] == "E2099"


def test_empty_body_is_not_cached(tmp_path):
    with EuroleagueClient(raw_dir=tmp_path, min_interval=0) as c:
        c._get_json = lambda url, params=None: None
        data, _ = c.game_file("E2099", 2, "Points")
        assert data is None
        assert not c.game_path("E2099", 2, "Points").exists()

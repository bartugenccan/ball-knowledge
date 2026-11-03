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


def test_empty_body_is_not_cached(tmp_path):
    with EuroleagueClient(raw_dir=tmp_path, min_interval=0) as c:
        c._get_json = lambda url, params=None: None
        data, _ = c.game_file("E2099", 2, "Points")
        assert data is None
        assert not c.game_path("E2099", 2, "Points").exists()

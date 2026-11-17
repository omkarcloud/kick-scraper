"""kick/fetch.py's Typesense search key on identity_pool: no network, the
bundle scan is faked. The pool's own rules live in tests/test_identity_pool.py.

    python -m pytest kick/test_fetch.py -q
"""
import threading
import time

import pytest

from kick import fetch


@pytest.fixture
def keys(monkeypatch):
    """The module's pool with a counting fake bundle scan."""
    pool = fetch._search_keys
    pool.clear()
    pool._last_mint.clear()
    pool._mint_times.clear()
    scans = []

    def scan(key, hint):
        time.sleep(0.05)                     # let the wave pile up behind one mint
        scans.append(key)
        return "ROTATEDKEY0000000000"

    monkeypatch.setattr(pool, "_mint_fn", scan)
    pool.scans = scans
    yield pool
    pool.clear()
    pool._last_mint.clear()
    pool._mint_times.clear()


def test_a_rejection_wave_costs_one_scan_and_none_inside_the_interval(keys, monkeypatch):
    accepted = {"ROTATEDKEY0000000000"}

    def fake_get_json(url, params=None, *, headers=None, label=None):
        if params["x-typesense-api-key"] not in accepted:
            raise fetch.KickBadRequest("Forbidden - a valid `x-typesense-api-key` header must be sent (login)")
        return {"found": 1, "hits": [{"document": {"q": params["q"]}}]}

    monkeypatch.setattr(fetch, "get_json", fake_get_json)
    assert fetch.search_key() == fetch.config.KICK_TYPESENSE_API_KEY, "the seed serves before any scan"

    results, errors = [], []

    def worker():
        try:
            results.append(fetch.typesense("channel", {"q": "xqc"}))
        except Exception as e:                # pragma: no cover - the assert below reports it
            errors.append(e)

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)
    assert not errors and len(results) == 8 and all(r["found"] == 1 for r in results)
    assert keys.scans == [""], "a wave of rejections across threads: ONE bundle scan"
    assert fetch.search_key() == "ROTATEDKEY0000000000"

    # the rotated key is rejected too: inside the interval the pool hands
    # back the same key and the call fails as it always did - no scan
    accepted.clear()
    with pytest.raises(fetch.KickUpstreamError, match="could not be refreshed"):
        fetch.typesense("channel", {"q": "xqc"})
    assert keys.scans == [""]

    # a real 400 (bad params) never touches the key
    def real_400(url, params=None, *, headers=None, label=None):
        raise fetch.KickBadRequest("Could not find a field named `nope`")

    monkeypatch.setattr(fetch, "get_json", real_400)
    with pytest.raises(fetch.KickBadRequest):
        fetch.typesense("channel", {"q": "xqc"})
    assert keys.scans == [""]

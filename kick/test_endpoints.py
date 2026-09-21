"""Live endpoint smoke tests: one call per /kick/* route against a running
service, with example values proven to return data (2026-09-21). The
listing tooling reads each route's FIRST call from this file's AST as its
working example, so the values stay literals.

Skipped unless KICK_BASE points at a running service:

    ONLY_SCRAPER=kick python run.py
    KICK_BASE=http://127.0.0.1:6002 python -m pytest kick/test_endpoints.py -q
"""
import os

import pytest

BASE = os.environ.get("KICK_BASE", "").rstrip("/")

pytestmark = pytest.mark.skipif(not BASE, reason="set KICK_BASE to run live endpoint tests")


def call(path, status=200, **params):
    from curl_cffi import requests
    resp = requests.get(BASE + path, params=params, timeout=180)
    assert resp.status_code == status, f"{path} {params} -> {resp.status_code} {resp.text[:300]}"
    body = resp.json()
    assert body, f"{path} returned an empty body"
    return body


def _live_slug():
    return call("/kick/livestreams", limit=1)["livestreams"][0]["channel"]["slug"]


def test_channels():
    assert call("/kick/channels/details", channel="xqc")["channel"]["followers_count"] > 1_000_000
    assert "is_live" in call("/kick/channels/status", channel="https://kick.com/xqc")
    batch = call("/kick/channels/status/batch", channels="xqc,adinross,amouranth")
    assert batch["count"] == 3
    assert call("/kick/channels/links", channel="xqc")["links"]
    assert call("/kick/channels/emotes", channel="xqc")["channel_emotes"]
    assert call("/kick/channels/recent-categories", channel="xqc")["categories"]
    assert call("/kick/channels/leaderboards", channel="xqc")["kicks"]["all_time"]["rows"]
    assert "poll" in call("/kick/channels/poll", channel="xqc")
    assert call("/kick/channels/prediction", channel="xqc")["prediction"]["outcomes"]
    assert "goals" in call("/kick/channels/goals", channel="xqc")
    assert "rewards" in call("/kick/channels/rewards", channel="xqc")
    assert call("/kick/channels/chatroom", channel="xqc")["chatroom"]["slow_mode"]
    assert call("/kick/channels/playback", channel="xqc")["playback_link"].startswith("https://")
    assert call("/kick/channels/chat-user", channel="xqc", user="xqc")["user"]["is_channel_owner"] is True
    assert "viewers" in call("/kick/channels/chatters", channel="xqc")
    assert call("/kick/channels/chatters", channel=_live_slug())["total_count"] > 0


def test_chat():
    page = call("/kick/chat/messages", channel="xqc")
    assert page["messages"] and page["next_cursor"]
    assert call("/kick/chat/messages", channel="xqc", cursor=page["next_cursor"])["messages"]


def test_videos():
    videos = call("/kick/videos", channel="xqc")["videos"]
    assert videos and videos[0]["playback_link"]
    # a VOD expires 30 days after its stream (this one: 2026-10-20)
    assert call("/kick/videos/details", video="d252b88b-188e-4d38-ac65-278ad209dff4")["video"]["duration_seconds"]
    assert call("/kick/videos/details", video=videos[0]["id"])["video"]["duration_seconds"]


def test_clips():
    page = call("/kick/clips", channel="xqc")
    assert page["clips"] and page["next_cursor"]
    assert call("/kick/clips", channel="xqc", cursor=page["next_cursor"])["clips"]
    assert call("/kick/clips/category", category="just-chatting")["clips"]
    assert call("/kick/clips/top", period="week")["clips"]
    assert call("/kick/clips/details", clip="clip_01H811MXG4FBR62FXPE1AXABDH")["clip"]["views_count"]


def test_livestreams():
    page = call("/kick/livestreams", limit=10)
    assert len(page["livestreams"]) == 10 and page["next_cursor"]
    assert call("/kick/livestreams", cursor=page["next_cursor"], limit=10)["livestreams"]
    assert call("/kick/livestreams", category="just-chatting", languages="en,es")["livestreams"]
    assert call("/kick/livestreams/featured", language="en")["livestreams"]
    assert call("/kick/livestreams/languages")["languages"]


def test_categories():
    assert call("/kick/categories", directory="games")["categories"]
    assert len(call("/kick/categories/directories")["directories"]) == 6
    assert call("/kick/categories/details", category="just-chatting")["category"]["followers_count"]


def test_search():
    assert call("/kick/search", query="gta")["categories"]
    assert call("/kick/search/channels", query="xqc")["channels"][0]["slug"] == "xqc"
    assert call("/kick/search/categories", query="counter strike")["categories"]


def test_errors():
    # paths via variables so the listing tooling never reads an error case
    # as a route's working example
    details, clip = "/kick/channels/details", "/kick/clips/details"
    call(details, status=404, channel="nopenope9x9x9")
    call(details, status=400, channel="https://twitch.tv/xqc")
    call(clip, status=404, clip="clip_01H811MXG4FBR62FXPE1AXABDX")

"""Offline tests: ref parsing and the normalizers against raw kick.com /
web.kick.com / search.kick.com responses captured 2026-09-21
(kick/fixtures/*.json).

    python -m pytest kick/test_parsers.py -q
"""
import json
import os

import pytest

from kick import parsers as P
from kick import refs

FIX = os.path.join(os.path.dirname(__file__), "fixtures")


def fx(name):
    with open(os.path.join(FIX, name + ".json")) as f:
        return json.load(f)


def _no_camel_or_url_keys(obj, path="$"):
    """Every emitted key is snake_case and no key is named *url*."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            assert key == key.lower() and " " not in key, f"{path}.{key} not snake_case"
            assert "url" not in key, f"{path}.{key} should be a *link"
            _no_camel_or_url_keys(value, f"{path}.{key}")
    elif isinstance(obj, list):
        for i, value in enumerate(obj):
            _no_camel_or_url_keys(value, f"{path}[{i}]")


# ---- refs -----------------------------------------------------------------------------

@pytest.mark.parametrize("value, expected", [
    ("xqc", "xqc"), ("XQC", "xqc"), ("@xqc", "xqc"),
    ("https://kick.com/xqc", "xqc"), ("https://kick.com/xqc/videos", "xqc"),
    ("kick.com/xqc?clip=clip_01H811MXG4FBR62FXPE1AXABDH", "xqc"),
    ("https://www.kick.com/Adin-Ross_1/", "adin-ross_1"),
])
def test_resolve_channel(value, expected):
    assert refs.resolve_channel(value) == expected


@pytest.mark.parametrize("value", ["https://twitch.tv/xqc", "https://kick.com/category/irl", "x q c", ""])
def test_resolve_channel_rejects(value):
    with pytest.raises(ValueError):
        refs.resolve_channel(value)


def test_resolve_channels():
    assert refs.resolve_channels("xqc, https://kick.com/adinross,XQC") == ["xqc", "adinross"]


@pytest.mark.parametrize("value, expected", [
    ("just-chatting", "just-chatting"),
    ("https://kick.com/category/just-chatting", "just-chatting"),
    ("https://kick.com/categories/grand-theft-auto-v/clips", "grand-theft-auto-v"),
])
def test_resolve_category(value, expected):
    assert refs.resolve_category(value) == expected


@pytest.mark.parametrize("value", [
    "clip_01H811MXG4FBR62FXPE1AXABDH",
    "https://kick.com/xqc/clips/clip_01H811MXG4FBR62FXPE1AXABDH",
    "https://kick.com/xqc?clip=clip_01H811MXG4FBR62FXPE1AXABDH",
])
def test_resolve_clip(value):
    assert refs.resolve_clip(value) == "clip_01H811MXG4FBR62FXPE1AXABDH"


def test_resolve_video():
    uuid = "d252b88b-188e-4d38-ac65-278ad209dff4"
    assert refs.resolve_video(uuid) == {"id": uuid, "channel": None}
    assert refs.resolve_video(f"https://kick.com/xqc/videos/{uuid}") == {"id": uuid, "channel": "xqc"}
    assert refs.resolve_video(f"https://kick.com/video/{uuid}") == {"id": uuid, "channel": None}
    with pytest.raises(ValueError):
        refs.resolve_video("https://kick.com/xqc/videos")


# ---- values -----------------------------------------------------------------------------

@pytest.mark.parametrize("raw, expected", [
    ("2026-09-21T09:05:54.000000Z", "2026-09-21T09:05:54Z"),
    ("2026-09-21 09:05:54", "2026-09-21T09:05:54Z"),
    ("2026-09-20T20:18:11+00:00", "2026-09-20T20:18:11Z"),
    ("2023-08-17T06:07:19.490719Z", "2023-08-17T06:07:19Z"),
    ("0001-01-01T00:00:00Z", None), ("", None), (None, None), ("junk", None),
])
def test_iso_datetime(raw, expected):
    assert P.iso_datetime(raw) == expected


def test_language_pair():
    table = {"by_name": {"polish": "pl"}, "by_code": {"pl": "Polish"}}
    assert P.language_pair("Polish", None, table) == ("Polish", "pl")
    assert P.language_pair("pl", None, table) == ("Polish", "pl")
    assert P.language_pair("English", "en", None) == ("English", "en")
    assert P.language_pair(None) == (None, None)


def test_socials_expand_handles():
    out = P.socials({"instagram": "xqcow1/", "twitter": "xqc", "youtube": "channel/UC1",
                     "discord": "/invite/abc", "tiktok": "@me", "facebook": ""})
    assert out == {"instagram": "https://instagram.com/xqcow1", "twitter": "https://x.com/xqc",
                   "youtube": "https://youtube.com/channel/UC1", "discord": "https://discord.gg/abc",
                   "tiktok": "https://tiktok.com/@me", "facebook": None}


# ---- entities ---------------------------------------------------------------------------------

def test_channel_details_offline():
    out = P.channel_details(fx("channel_v2"))
    assert out["id"] == 668 and out["slug"] == "xqc" and out["username"] == "xQc"
    assert out["link"] == "https://kick.com/xqc"
    assert isinstance(out["followers_count"], int) and out["followers_count"] > 1_000_000
    assert out["is_live"] is False and out["livestream"] is None
    assert out["is_verified"] is True
    assert out["subscriber_badges"] and out["subscriber_badges"][0]["image"].startswith("https://")
    assert out["chatroom"]["followers_mode"]["is_enabled"] is True
    assert out["recent_categories"][0]["slug"] == "just-chatting"
    _no_camel_or_url_keys(out)


def test_channel_details_live():
    out = P.channel_details(fx("channel_live_v2"))
    live = out["livestream"]
    assert out["is_live"] is True and live["is_live"] is True
    assert live["viewer_count"] > 0 and live["started_at"].endswith("Z")
    assert live["language"] and live["language_code"]
    assert "channel" not in live          # the response is already about this channel
    assert live["category"]["link"].startswith("https://kick.com/category/")


def test_livestream_web_row():
    row = fx("livestreams_web")["data"]["livestreams"][0]
    out = P.livestream(row, languages={"by_code": {"en": "English"}})
    assert isinstance(out["id"], str) and out["title"]
    assert out["language_code"] == row["language"]
    assert out["channel"]["slug"] == row["channel"]["slug"]
    assert out["thumbnail"]["hd_link"] and "1080" in out["thumbnail"]["hd_link"]
    assert set(out["category"]) == {"id", "name", "slug", "link"}
    _no_camel_or_url_keys(out)


def test_livestream_legacy_row():
    row = fx("stream_livestreams")["data"][0]
    out = P.livestream(row, languages={"by_name": {"japanese": "ja"}})
    assert out["language"] == "Japanese" and out["language_code"] == "ja"
    assert out["channel"]["username"] and out["channel"]["link"]


def test_emote_sets():
    sets = P.emote_sets(fx("emotes"))
    assert len(sets["channel"]) == 25 and sets["global"] and sets["emoji"]
    assert sets["channel"][0]["image"].startswith("https://files.kick.com/emotes/")


def test_leaderboards():
    subs = P.gift_leaderboards(fx("leaderboards"))
    kicks = P.kicks_leaderboards(fx("kicks_leaderboard")["data"])
    for board in (subs, kicks):
        assert board["all_time"]["rows"][0]["rank"] == 1
        assert board["all_time"]["rows"][0]["quantity"] > 0
        assert "profile_image" not in board["all_time"]["rows"][0]["user"]


def test_prediction_poll_goal_reward():
    pred = P.prediction(fx("prediction_latest")["data"]["prediction"])
    assert pred["state"] == "RESOLVED" and sum(o["is_winner"] for o in pred["outcomes"]) == 1
    poll = P.poll(fx("polls_sample")["data"]["poll"])
    assert poll["votes_count"] == sum(o["votes_count"] for o in poll["options"])
    assert round(sum(o["votes_percent"] for o in poll["options"])) == 100
    goal = P.goal(fx("goals_sample")[0])
    assert goal["target"] == 1000 and goal["progress_percent"] == 4.1
    reward = P.reward(fx("rewards_sample")["data"][0])
    assert reward["cost"] == 50000 and reward["is_enabled"] is True
    assert P.poll(None) is None and P.prediction({}) is not None


def test_chatroom_blocks():
    room = P.chatroom(fx("chatroom"), rules="")
    assert room["followers_mode"] == {"is_enabled": True, "min_follow_minutes": 60}
    assert room["rules"] is None and "mode" not in room
    flat = P.chatroom(fx("channel_v2")["chatroom"])
    assert flat["mode"] == "public" and "rules" not in flat and "account_age" not in flat


def test_chat_history():
    out = P.chat_history(fx("chat_messages")["data"])
    assert len(out["messages"]) == 25 and out["next_cursor"]
    first = out["messages"][0]
    assert first["emotes"] and first["emotes"][0]["name"] == "catKISS"
    assert first["text"] == "catKISS"
    replies = [m for m in out["messages"] if m["type"] == "reply"]
    assert replies and replies[0]["reply_to"]["content"] == "!playlist"
    assert replies[0]["reply_to"]["sender"]["username"] == "kotidestroyer"
    mod = [m for m in out["messages"] if any(b["type"] == "moderator" for b in m["sender"]["badges"])]
    assert mod
    _no_camel_or_url_keys(out)


def test_chatters():
    out = P.chatters(fx("active_chatters")["data"])
    assert out["total_count"] >= len(out["viewers"]) and out["moderators"]
    assert "id" not in out["viewers"][0]


def test_video_three_spellings():
    legacy_row = P.video(fx("videos_v2")[0])
    v1 = P.video(fx("video_v1"))
    web = P.video(fx("video_web")["data"])
    assert legacy_row["id"] == v1["id"] == "d252b88b-188e-4d38-ac65-278ad209dff4"
    assert legacy_row["duration_seconds"] == v1["duration_seconds"] == web["duration_seconds"] == 41486
    assert legacy_row["duration"] == "11:31:26"
    assert legacy_row["playback_link"].endswith(".m3u8")
    assert v1["thumbnail"] is None                 # presigned S3 link dropped
    assert v1["link"].endswith("01a0c078-17b8-7021-8b7e-f84923e063e4")
    assert web["ended_at"] and web["expires_at"]
    for item in (legacy_row, v1, web):
        _no_camel_or_url_keys(item)


def test_clip_two_spellings():
    v2 = P.clip(fx("clip_v2")["clip"])
    web = P.clip(fx("clip_web")["data"])
    for item in (v2, web):
        assert item["id"] == "clip_01H811MXG4FBR62FXPE1AXABDH"
        assert item["playback_link"].endswith(".m3u8")
        assert item["link"] == "https://kick.com/xqc/clips/clip_01H811MXG4FBR62FXPE1AXABDH"
        assert item["views_count"] > 300000
        _no_camel_or_url_keys(item)
    assert v2["likes_count"] == 0 and v2["creator"]["profile_image"]
    zero = P.clip(fx("clips_channel_v2")["clips"][0])
    assert zero["clipped_at"] is None              # upstream zero date


def test_categories():
    row = P.category_ref(fx("subcategories")["data"][0])
    assert row["viewer_count"] > 0 and row["directory"]["slug"] == "irl"
    detail = P.category_ref(fx("subcategory"))
    assert detail["followers_count"] > 0 and detail["banner"]
    doc = P.category_ref(fx("typesense_categories")["hits"][0]["document"])
    assert doc["directory"]["slug"] == "games" and doc["directory"]["id"] == 1 and doc["banner"]
    page = P.laravel_pagination(fx("subcategories"), 1, 5)
    assert page == {"page": 1, "items_per_page": 5, "total_pages": 2586, "total_count": 12930}


def test_search_rows():
    ch = P.search_channel(fx("search_enriched")["data"]["channels"][0])
    assert ch["followers_count"] and ch["is_verified"] is not None
    ts = P.typesense_channel(fx("typesense_channels")["hits"][0]["document"])
    assert ts["slug"] == "xqc" and ts["followers_count"] > 1_000_000


def test_partial_payloads_never_crash():
    for fn in (P.channel_details, P.livestream, P.video, P.clip, P.category_ref, P.chat_message,
               P.poll, P.prediction, P.goal, P.reward, P.user_profile, P.chat_user_card):
        assert fn(None) is None
        fn({})                                  # must not raise
    P.chat_history(None), P.chatters(None), P.emote_sets(None)
    P.gift_leaderboards({}), P.kicks_leaderboards({})

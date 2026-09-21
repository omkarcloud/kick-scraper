"""Lookups shared by the /kick/* endpoint modules: slug -> numeric channel
id (the web.kick.com routes and the chat history take the id, not the
slug), category slug -> id, the six root directories and the language
table. All memoised in-process — ids never change, the tables change a few
times a year."""
import threading
import time

from kick import parsers as P
from kick.fetch import KickNotFound, legacy, web_optional

ID_TTL = 24 * 3600
TABLE_TTL = 6 * 3600

_lock = threading.Lock()
_memo = {}


def memo(key, ttl, build):
    now = time.time()
    with _lock:
        hit = _memo.get(key)
        if hit and hit[0] > now:
            return hit[1]
    value = build()
    with _lock:
        _memo[key] = (now + ttl, value)
    return value


def remember(key, ttl, value):
    with _lock:
        _memo[key] = (time.time() + ttl, value)


# ---- channels -----------------------------------------------------------------

def channel_raw(slug):
    """The v2 channel object (fresh, never memoised: it carries live state).
    Also seeds the slug -> id memo."""
    try:
        obj = legacy(f"/api/v2/channels/{slug}")
    except KickNotFound:
        raise KickNotFound(f"channel '{slug}' not found")
    if not isinstance(obj, dict) or obj.get("id") is None:
        raise KickNotFound(f"channel '{slug}' not found")
    remember(("channel_id", slug), ID_TTL, P.to_int(obj.get("id")))
    return obj


def channel_id(slug):
    """slug -> numeric channel id (the chatroom id is the same number on
    every channel checked, but the channel id is what the routes take).
    Uses the light /info object on a miss."""
    def build():
        try:
            obj = legacy(f"/api/v2/channels/{slug}/info")
        except KickNotFound:
            raise KickNotFound(f"channel '{slug}' not found")
        if not isinstance(obj, dict) or obj.get("id") is None:
            raise KickNotFound(f"channel '{slug}' not found")
        return P.to_int(obj["id"])
    return memo(("channel_id", slug), ID_TTL, build)


# ---- categories ------------------------------------------------------------------

def category_raw(slug):
    try:
        obj = legacy(f"/api/v1/subcategories/{slug}")
    except KickNotFound:
        raise KickNotFound(f"category '{slug}' not found")
    if not isinstance(obj, dict) or obj.get("id") is None:
        raise KickNotFound(f"category '{slug}' not found")
    remember(("category_id", slug), ID_TTL, P.to_int(obj.get("id")))
    return obj


def category_id(slug):
    return memo(("category_id", slug), ID_TTL, lambda: P.to_int(category_raw(slug)["id"]))


def directories():
    """The six root directories [{id, name, slug, icon}] (Games, IRL, Music,
    Gambling, Creative, Alternative)."""
    def build():
        rows = legacy("/api/v1/categories") or []
        return [P.directory_ref(r) for r in rows if isinstance(r, dict)]
    return memo("directories", TABLE_TTL, build)


def directory_id(slug):
    for row in directories():
        if row.get("slug") == slug:
            return row["id"]
    raise ValueError(f"unknown directory '{slug}' — one of "
                     f"{', '.join(r['slug'] for r in directories() if r.get('slug'))}")


# ---- languages ---------------------------------------------------------------------

def languages():
    """{"list": [{code, name}], "by_name": {name.lower(): code},
    "by_code": {code: name}, "live_codes": [codes the live directory
    currently filters on]}."""
    def build():
        rows = legacy("/stream/languages") or []
        table = [{"code": P.text(r.get("code")), "name": P.text(r.get("name"))}
                 for r in rows if isinstance(r, dict) and r.get("code")]
        live = web_optional("/livestreams/language-codes") or []
        return {
            "list": table,
            "by_name": {r["name"].lower(): r["code"] for r in table if r["name"]},
            "by_code": {r["code"]: r["name"] for r in table},
            "live_codes": [c for c in live if isinstance(c, str)],
        }
    try:
        return memo("languages", TABLE_TTL, build)
    except Exception:
        # A language name is decoration: never fail an endpoint over it.
        return {"list": [], "by_name": {}, "by_code": {}, "live_codes": []}

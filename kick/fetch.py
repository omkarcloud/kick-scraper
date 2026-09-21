"""Kick transport: plain curl_cffi with browser-impersonated TLS. No browser,
no cookies, no token (validated 2026-09-21 from direct Indian egress and
through residential US/DE proxy exits; a 40-request burst from one IP all 200).
Kick's Kasada protection (the "kpsdk solver" listings on RapidAPI exist for
it) guards login, chat SEND and other POST flows — none of the public GET
surfaces this package reads.

Three upstream hosts, all open JSON:

  * LEGACY  https://kick.com/api/v1|v2/...  and  /stream/..., /emotes/...
    The original Laravel API the old SPA used and the current app still
    calls for channel objects, chat history, clips, categories and the
    localized livestream directory. Laravel pagination (page/limit) where it
    pages at all; `tags` must be ONE string (tags[] -> 422); the channel
    videos list ignores its cursor (always the newest 24).

  * WEB     https://web.kick.com/api/v1/...
    The newer Go API the current Next.js app prefers. Real cursor
    pagination (data.pagination.next_cursor / data.cursor), livestream
    browse with sort/language/category/tag filters, channel videos + clips
    by channel ID, Kicks leaderboards, active chatters. 400 for any unknown
    param value, 403 for the auth-only recommendation feeds.

  * SEARCH  https://search.kick.com/api/v1/search[/enriched]?query=
            https://search.kick.com/collections/<collection>/documents/search
    The enriched search is open; the Typesense document search needs the
    public search-only key the site ships in its JS bundle
    (NEXT_PUBLIC_TYPESENSE_API_KEY). config.KICK_TYPESENSE_API_KEY seeds it
    and a 401 re-harvests it from the bundle once, so a rotation self-heals.

Blocks: none seen. If the pod's egress ever starts answering 403/429, a
worker moves its session to a sticky residential proxy exit
(config.kick_fallback_proxy()) for
config.KICK_BLOCK_COOLDOWN seconds (config.KICK_FALLBACK_PROXY_COUNTRY),
the same shape as the soundcloud transport.

Failure taxonomy (scraper_errors, mapped to HTTP by route_glue):
  KickUpstreamError  transport failure / 5xx            — retryable
  KickBlocked        403 / 429 / HTML where JSON expected — retryable on a new exit
  KickBadRequest     upstream 400 / 422                   — never retried
  KickNotFound       404 / missing entity                 — never retried
"""
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from scraper_errors import BadRequest, Blocked, NotFound, UpstreamError

SITE = "https://kick.com"
WEB = "https://web.kick.com"
SEARCH = "https://search.kick.com"
IMPERSONATE = "chrome"

TIMEOUT = 45
PAGE_TIMEOUT = 60
FANOUT_WORKERS = 6

HEADERS = {
    "accept": "application/json",
    "accept-language": "en-US,en;q=0.9",
    "referer": SITE + "/",
    "origin": SITE,
}
PAGE_HEADERS = {
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "accept-language": "en-US,en;q=0.9",
    "upgrade-insecure-requests": "1",
}


class KickUpstreamError(UpstreamError):
    """Transport failure or 5xx — retryable."""


class KickBlocked(KickUpstreamError, Blocked):
    """403 / 429 or an HTML body where JSON was expected — retryable."""


class KickBadRequest(BadRequest):
    """Upstream 400 / 422 — the params were rejected. Never retried."""


class KickNotFound(NotFound):
    """Entity / page does not exist — never retried."""


# ---- sessions ------------------------------------------------------------------
# One curl session per worker thread. Direct egress by default; after a block
# the thread's sessions go through a sticky residential exit for a cooldown.
_local = threading.local()
_fallback_until = 0.0
_fallback_lock = threading.Lock()


def _proxy_for_new_session():
    forced = config.kick_proxy()
    if forced:
        return forced
    if time.time() < _fallback_until:
        return config.kick_fallback_proxy()
    return None


def _session():
    sess = getattr(_local, "session", None)
    if sess is None:
        from curl_cffi import requests as curl_requests
        sess = curl_requests.Session(impersonate=IMPERSONATE)
        proxy = _proxy_for_new_session()
        if proxy:
            sess.proxies = {"http": proxy, "https": proxy}
        _local.session = sess
    return sess


def _drop_session():
    sess = getattr(_local, "session", None)
    _local.session = None
    if sess is not None:
        try:
            sess.close()
        except Exception:
            pass


def _note_block():
    """A 403/429 on direct egress: send new sessions through a residential
    exit for a while (no-op when no fallback country is configured)."""
    global _fallback_until
    if config.kick_fallback_proxy() is not None:
        with _fallback_lock:
            _fallback_until = time.time() + config.KICK_BLOCK_COOLDOWN


def dump_debug(name, text):
    dbg = os.environ.get("KICK_DEBUG_DIR", "")
    if dbg and text:
        try:
            os.makedirs(dbg, exist_ok=True)
            with open(os.path.join(dbg, name + ".txt"), "w") as f:
                f.write(text)
        except OSError:
            pass


# ---- requests --------------------------------------------------------------------

def _classify(resp, label):
    status = resp.status_code
    if status == 404:
        raise KickNotFound(f"{label} not found")
    if status in (403, 429):
        dump_debug("blocked", resp.text)
        _note_block()
        raise KickBlocked(f"HTTP {status} on {label}")
    if status in (400, 422):
        raise KickBadRequest(_error_message(resp) or f"upstream rejected {label}")
    if status == 401:
        # auth-only surface (or a rotated typesense key, handled by the caller)
        raise KickBadRequest(f"{label} needs a Kick login")
    if status >= 500 or status not in (200, 204):
        raise KickUpstreamError(f"HTTP {status} on {label}")


def _error_message(resp):
    try:
        body = resp.json()
    except Exception:
        return None
    if not isinstance(body, dict):
        return None
    message = body.get("message")
    errors = body.get("errors")
    if isinstance(errors, dict):
        flat = "; ".join(f"{k}: {' '.join(v) if isinstance(v, list) else v}" for k, v in errors.items())
        return f"{message}: {flat}" if message else flat
    if isinstance(message, str) and message.strip():
        return message.strip()
    data = body.get("data")
    if isinstance(data, dict) and data.get("type"):
        return str(data["type"])
    return None


def _json_of(resp, label):
    body = resp.text or ""
    if resp.status_code == 204 or not body.strip():
        return None
    if not body.lstrip().startswith(("{", "[")):
        dump_debug("nonjson", body)
        raise KickBlocked(f"{label} returned HTML, not JSON")
    try:
        return resp.json()
    except Exception:
        dump_debug("badjson", body)
        raise KickUpstreamError(f"could not parse JSON from {label}")


def _retrying(fn):
    last = None
    for attempt in range(1, config.MAX_RETRIES + 1):
        try:
            return fn()
        except KickUpstreamError as e:      # includes KickBlocked
            last = e
            _drop_session()
        if attempt < config.MAX_RETRIES:
            time.sleep(config.RETRY_BACKOFF * attempt)
    raise last


def get_json(url, params=None, *, headers=None, label=None):
    """GET one JSON endpoint on any of the three hosts. `params` values that
    are None are dropped; list values repeat the key (language=en&language=es)."""
    label = label or url.replace(SITE, "").replace(WEB, "web:").replace(SEARCH, "search:")
    query = {}
    for key, value in (params or {}).items():
        if value is None or value == "" or value == []:
            continue
        query[key] = value

    def once():
        sess = _session()
        try:
            resp = sess.get(url, params=query, headers=headers or HEADERS, timeout=TIMEOUT,
                            allow_redirects=True)
        except Exception as e:
            raise KickUpstreamError(f"request failed: {type(e).__name__}: {e}")
        _classify(resp, label)
        return _json_of(resp, label)

    return _retrying(once)


def get_json_optional(url, params=None, **kwargs):
    """Like get_json but a 404 / 400 / 401 yields None (optional tabs)."""
    try:
        return get_json(url, params, **kwargs)
    except (KickNotFound, KickBadRequest):
        return None


def legacy(path, params=None, **kwargs):
    """GET https://kick.com<path>."""
    return get_json(SITE + path, params, **kwargs)


def legacy_optional(path, params=None, **kwargs):
    return get_json_optional(SITE + path, params, **kwargs)


def web(path, params=None, **kwargs):
    """GET https://web.kick.com/api/v1<path> -> the `data` member."""
    body = get_json(WEB + "/api/v1" + path, params, **kwargs)
    if isinstance(body, dict) and "data" in body:
        return body["data"]
    return body


def web_optional(path, params=None, **kwargs):
    try:
        return web(path, params, **kwargs)
    except (KickNotFound, KickBadRequest):
        return None


def search_api(path, params=None):
    """GET https://search.kick.com/api/v1<path> -> the `data` member."""
    body = get_json(SEARCH + "/api/v1" + path, params)
    if isinstance(body, dict) and "data" in body:
        return body["data"]
    return body


def get_page(path):
    """GET one kick.com HTML page (only used to re-harvest the search key)."""
    def once():
        sess = _session()
        try:
            resp = sess.get(SITE + path, headers=PAGE_HEADERS, timeout=PAGE_TIMEOUT,
                            allow_redirects=True)
        except Exception as e:
            raise KickUpstreamError(f"request failed: {type(e).__name__}: {e}")
        _classify(resp, path)
        return resp.text or ""
    return _retrying(once)


# ---- typesense search key --------------------------------------------------------
# The site's search-only Typesense key is a build constant in one of the
# _next chunks (NEXT_PUBLIC_TYPESENSE_API_KEY). Seeded from config; on a 401
# the chunks referenced by the homepage are scanned once for a new value.
_KEY_RE = re.compile(r'NEXT_PUBLIC_TYPESENSE_API_KEY\s*:\s*(?:o\.z\.string\(\)\.min\(1\)\.default\()?"([A-Za-z0-9]{16,64})"')
_SCRIPT_RE = re.compile(r'<script[^>]+src="([^"]+\.js)"')
_search_key = None
_key_lock = threading.Lock()


def search_key():
    global _search_key
    if _search_key is None:
        _search_key = config.KICK_TYPESENSE_API_KEY
    return _search_key


def _refresh_search_key(stale=None):
    """Re-read the key from the site's JS bundle. Returns the new value or None.
    `stale` is the key that was just rejected: when another thread already
    rotated past it while this one waited for the lock, that key is reused."""
    global _search_key
    with _key_lock:
        current = _search_key
        if stale is not None and current is not None and current != stale:
            return current
        try:
            html = get_page("/")
        except Exception as e:
            print(f"kick: search key refresh failed: {type(e).__name__}: {e}")
            return None
        sess = _session()
        for src in _SCRIPT_RE.findall(html):
            if src.startswith("//"):
                src = "https:" + src
            elif not src.startswith("http"):
                src = SITE + src
            try:
                js = sess.get(src, headers=PAGE_HEADERS, timeout=PAGE_TIMEOUT).text or ""
            except Exception:
                continue
            match = _KEY_RE.search(js)
            if match:
                found = match.group(1)
                if found == current:
                    return None
                print(f"kick: typesense key rotated {current} -> {found}")
                _search_key = found
                return found
        print("kick: typesense key not found in the bundle")
        return None


def typesense(collection, params):
    """GET one Typesense document search -> the raw result body."""
    url = f"{SEARCH}/collections/{collection}/documents/search"

    def call(key):
        query = dict(params)
        query["x-typesense-api-key"] = key
        return get_json(url, query, label=f"search {collection}")

    used = search_key()
    try:
        return call(used)
    except KickBadRequest as e:
        if "login" not in str(e):        # a real 400: bad params
            raise
        fresh = _refresh_search_key(used)
        if fresh is None:
            raise KickUpstreamError("kick search key rejected and could not be refreshed")
        return call(fresh)


# ---- fan-out ------------------------------------------------------------------------

def run_parallel(fns):
    if not fns:
        return []
    if len(fns) == 1:
        return [fns[0]()]
    with ThreadPoolExecutor(max_workers=min(FANOUT_WORKERS, len(fns))) as ex:
        futures = [ex.submit(fn) for fn in fns]
        return [f.result() for f in futures]


def gather(mapping):
    """{key: callable} in parallel -> {key: result}; a NotFound / BadRequest
    for one key yields None instead of failing the set."""
    keys = list(mapping)

    def guarded(fn):
        def run():
            try:
                return fn()
            except (KickNotFound, KickBadRequest):
                return None
        return run

    results = run_parallel([guarded(mapping[k]) for k in keys])
    return dict(zip(keys, results))


if __name__ == "__main__":
    # Smoke test: python kick/fetch.py [slug]
    slug = sys.argv[1] if len(sys.argv) > 1 else "xqc"
    channel = legacy(f"/api/v2/channels/{slug}")
    print(f"channel {slug}: id={channel.get('id')} followers={channel.get('followers_count')}")
    live = web("/livestreams", {"limit": 3, "sort": "viewer_count_desc"})
    print("top live:", [(r["channel"]["slug"], r["viewer_count"]) for r in live["livestreams"]])
    hits = typesense("channel", {"q": slug, "query_by": "username", "per_page": 3})
    print("search:", [h["document"]["slug"] for h in hits.get("hits", [])])

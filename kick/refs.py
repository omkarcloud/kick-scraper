"""Kick reference parsing: ONE param per input that auto-detects its forms
(tripadvisor QueryOrIdField convention — never a sibling `url`/`id` pair).

  channel    xqc | https://kick.com/xqc | https://kick.com/xqc/videos | kick.com/xqc?clip=...
  category   just-chatting | https://kick.com/category/just-chatting
                           | https://kick.com/categories/just-chatting/clips
  clip       clip_01H811MXG4FBR62FXPE1AXABDH | https://kick.com/xqc/clips/clip_01H8...
                                             | https://kick.com/xqc?clip=clip_01H8...
  video      d252b88b-188e-4d38-ac65-278ad209dff4 (v1 video uuid)
             | 01a0c078-17b8-7021-8b7e-f84923e063e4 (web video id, also a uuid)
             | https://kick.com/xqc/videos/<uuid> | https://kick.com/video/<uuid>

Kick slugs are lower-case [a-z0-9_-]; the site itself lower-cases the path,
so `XQC` and `xqc` are the same channel.
"""
import re
from urllib.parse import parse_qs, urlparse

SITE = "https://kick.com"

_SLUG_RE = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")
_CLIP_RE = re.compile(r"^clip_[A-Z0-9]{20,32}$", re.I)
_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
_RESERVED = {"category", "categories", "browse", "video", "videos", "clips", "clip", "search",
             "following", "dashboard", "settings", "terms", "privacy", "community-guidelines",
             "creator", "creators", "kicks", "login", "register", "api", "stream", "emotes"}


def _is_url(value):
    return value.startswith(("http://", "https://", "//")) or value.lower().startswith(("kick.com/", "www.kick.com/"))


def _parts(value):
    """A kick.com link -> (path segments, query dict). Raises ValueError for
    another site."""
    url = value
    if url.startswith("//"):
        url = "https:" + url
    elif not url.startswith("http"):
        url = "https://" + url
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if not (host == "kick.com" or host.endswith(".kick.com")):
        raise ValueError("not a kick.com link")
    segments = [s for s in parsed.path.split("/") if s]
    return segments, parse_qs(parsed.query)


def channel_link(slug):
    return f"{SITE}/{slug}" if slug else None


def category_link(slug):
    return f"{SITE}/category/{slug}" if slug else None


def clip_link(channel_slug, clip_id):
    if not clip_id:
        return None
    return f"{SITE}/{channel_slug}/clips/{clip_id}" if channel_slug else f"{SITE}/clips/{clip_id}"


def video_link(channel_slug, video_id):
    if not video_id:
        return None
    return f"{SITE}/{channel_slug}/videos/{video_id}" if channel_slug else f"{SITE}/video/{video_id}"


def resolve_channel(value):
    """Channel slug or any kick.com channel link -> the lower-case slug."""
    value = str(value or "").strip()
    if not value:
        raise ValueError("channel is required")
    if _is_url(value):
        try:
            segments, _ = _parts(value)
        except ValueError:
            raise ValueError("channel must be a kick.com channel link (https://kick.com/xqc) or a slug")
        if not segments or segments[0].lower() in _RESERVED:
            raise ValueError("channel link must point at a channel page (https://kick.com/xqc)")
        value = segments[0]
    value = value.lstrip("@")
    if not _SLUG_RE.match(value):
        raise ValueError("channel must be a Kick slug (letters, digits, _ or -) or a kick.com link")
    return value.lower()


def resolve_channels(value):
    """Comma-separated slugs / links -> [slug, ...] (deduped, order kept)."""
    out = []
    for raw in str(value or "").split(","):
        raw = raw.strip()
        if not raw:
            continue
        slug = resolve_channel(raw)
        if slug not in out:
            out.append(slug)
    if not out:
        raise ValueError("channels is required")
    return out


def resolve_category(value):
    """Category slug or a kick.com category link -> the slug."""
    value = str(value or "").strip()
    if not value:
        raise ValueError("category is required")
    if _is_url(value):
        try:
            segments, _ = _parts(value)
        except ValueError:
            raise ValueError("category must be a kick.com category link or a slug")
        if len(segments) >= 2 and segments[0].lower() in ("category", "categories"):
            value = segments[1]
        else:
            raise ValueError("category link must look like https://kick.com/category/just-chatting")
    value = value.split("?")[0].split("#")[0]
    if not _SLUG_RE.match(value):
        raise ValueError("category must be a Kick category slug (just-chatting) or a kick.com link")
    return value.lower()


def resolve_clip(value):
    """Clip id (clip_01H8...) or a kick.com clip link -> the clip id."""
    value = str(value or "").strip()
    if not value:
        raise ValueError("clip is required")
    if _is_url(value):
        try:
            segments, query = _parts(value)
        except ValueError:
            raise ValueError("clip must be a kick.com clip link or a clip id")
        candidate = None
        if query.get("clip"):
            candidate = query["clip"][0]
        else:
            for segment in reversed(segments):
                if _CLIP_RE.match(segment):
                    candidate = segment
                    break
        if not candidate:
            raise ValueError("clip link must contain a clip id (https://kick.com/xqc/clips/clip_01H8...)")
        value = candidate
    if not _CLIP_RE.match(value):
        raise ValueError("clip must be a Kick clip id (clip_01H811MXG4FBR62FXPE1AXABDH) or a kick.com link")
    return value


def resolve_video(value):
    """Video uuid or a kick.com video link -> {"id": uuid, "channel": slug|None}."""
    value = str(value or "").strip()
    if not value:
        raise ValueError("video is required")
    channel = None
    if _is_url(value):
        try:
            segments, _ = _parts(value)
        except ValueError:
            raise ValueError("video must be a kick.com video link or a video id")
        candidate = None
        for index, segment in enumerate(segments):
            if _UUID_RE.match(segment):
                candidate = segment
                if index >= 2 and segments[index - 1].lower() in ("videos", "video"):
                    channel = segments[index - 2].lower()
                break
        if not candidate:
            raise ValueError("video link must contain a video id (https://kick.com/xqc/videos/<uuid>)")
        value = candidate
    if not _UUID_RE.match(value):
        raise ValueError("video must be a Kick video id (uuid) or a kick.com video link")
    return {"id": value.lower(), "channel": channel}

"""/kick/clips/* — clip lists (per channel, per category, site-wide) and
one clip. All lists come from the legacy v2 clip API: it alone carries
likes, privacy and the VOD offset, and it takes the time window the web
API lacks. Paging is an opaque cursor (the previous page's next_cursor);
20 clips per page."""
from kick import parsers as P
from kick.fetch import KickNotFound, gather, legacy, web_optional


def _page(path, sort, period, cursor, not_found):
    try:
        body = legacy(path, {"cursor": cursor or 0, "sort": sort, "time": period})
    except KickNotFound:
        raise KickNotFound(not_found)
    body = body if isinstance(body, dict) else {}
    clips = [P.clip(c) for c in (body.get("clips") or []) if isinstance(c, dict)]
    return {
        "sort": {"view": "views", "date": "date"}.get(sort, sort),
        "period": period,
        "count": len(clips),
        "next_cursor": P.clip_cursor(body.get("nextCursor")) if clips else None,
        "clips": clips,
    }


def channel_clips(channel, sort="view", period="all", cursor=None):
    out = _page(f"/api/v2/channels/{channel}/clips", sort, period, cursor,
                f"channel '{channel}' not found")
    for item in out["clips"]:
        P.without_channel(item)
    return {"channel": channel, **out}


def category_clips(category, sort="view", period="week", cursor=None):
    out = _page(f"/api/v2/categories/{category}/clips", sort, period, cursor,
                f"category '{category}' not found")
    return {"category": category, **out}


def top_clips(sort="view", period="day", cursor=None):
    return _page("/api/v2/clips", sort, period, cursor, "no clips")


def details(clip):
    """One clip. The v2 object is the full one; the web object adds the
    channel's live state and the true clip start where v2 has the zero date."""
    parts = gather({
        "v2": lambda: legacy(f"/api/v2/clips/{clip}"),
        "web": lambda: web_optional(f"/clips/{clip}"),
    })
    raw = (parts["v2"] or {}).get("clip") if isinstance(parts["v2"], dict) else None
    extra = parts["web"] if isinstance(parts["web"], dict) else None
    if not isinstance(raw, dict) and not extra:
        raise KickNotFound(f"clip '{clip}' not found")
    item = P.clip(raw if isinstance(raw, dict) else extra)
    if extra:
        if item["clipped_at"] is None:
            item["clipped_at"] = P.iso_datetime(extra.get("started_at"))
        live = (extra.get("channel") or {}).get("is_live") if isinstance(extra.get("channel"), dict) else None
        if item["channel"] is not None:
            item["channel"]["is_live"] = P.bool_or_none(live)
    return {"clip": item}

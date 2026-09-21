"""/kick/videos/* — a channel's past broadcasts (VODs) and one VOD.

Two upstream spellings are stitched: the legacy list (kick.com/api/v2/
channels/<slug>/videos: views, the HLS source, full category objects,
the stable video uuid) and the web list (web.kick.com: end time, expiry of
the 30-day VOD, the web id the new site links with). Rows are joined on the
broadcast start time. Kick serves the latest 24 VODs only — neither list
pages (their cursor/page params are ignored upstream)."""
from kick import parsers as P
from kick import shared
from kick.fetch import KickNotFound, gather, legacy, web, web_optional


def _web_extras(row):
    """What only the web spelling carries, keyed for the merge."""
    return {
        "web_id": P.text(row.get("id")),
        "thumbnail": P.thumbnail(row.get("thumbnail")) if isinstance(row.get("thumbnail"), dict) else None,
        "ended_at": P.iso_datetime(row.get("end_time")),
        "expires_at": P.iso_datetime(row.get("original_expires_at")),
        "playback_link": P.text(row.get("recording_url")),
    }


def _merge(video, extras, channel=None):
    """Fold the web-only fields in. The web id is what kick.com links a VOD
    with, and the web thumbnail is a stable images.kick.com link (the v1
    record's is a presigned S3 URL that expires in 5 minutes)."""
    if not extras:
        return video
    for key in ("ended_at", "expires_at", "playback_link"):
        if video.get(key) is None and extras.get(key):
            video[key] = extras[key]
    if extras.get("thumbnail"):
        video["thumbnail"] = extras["thumbnail"]
    slug = channel or (video.get("channel") or {}).get("slug")
    if extras.get("web_id") and slug:
        video["link"] = P.refs.video_link(slug, extras["web_id"])
    return video


def channel_videos(channel):
    cid = shared.channel_id(channel)
    parts = gather({
        "legacy": lambda: legacy(f"/api/v2/channels/{channel}/videos"),
        "web": lambda: web(f"/channels/{cid}/videos"),
    })
    languages = shared.languages()
    chan_ref = None
    by_start = {}
    for row in parts["web"] if isinstance(parts["web"], list) else []:
        if isinstance(row, dict):
            by_start[P.iso_datetime(row.get("start_time"))] = _web_extras(row)
            if chan_ref is None and isinstance(row.get("channel"), dict):
                chan_ref = P.channel_ref(row["channel"])
    chan_ref = chan_ref or P.channel_ref(None, slug=channel)
    videos = []
    for row in parts["legacy"] if isinstance(parts["legacy"], list) else []:
        if not isinstance(row, dict):
            continue
        item = P.without_channel(P.video(row, channel=chan_ref, languages=languages))
        videos.append(_merge(item, by_start.pop(item["started_at"], None), channel))
    if not videos:
        # legacy list failed or empty: fall back to the web rows alone
        for row in parts["web"] if isinstance(parts["web"], list) else []:
            if isinstance(row, dict):
                videos.append(P.without_channel(P.video(row, languages=languages)))
    return {"channel": channel, "count": len(videos), "videos": videos}


def details(video):
    """One VOD by its id (the uuid in /api/v1/video/<uuid> and in every
    `videos[].id` this API returns) or a kick.com video link. The newer web
    id also works when the link carries the channel
    (https://kick.com/<channel>/videos/<web id>)."""
    vid, channel = video["id"], video.get("channel")
    languages = shared.languages()
    try:
        obj = legacy(f"/api/v1/video/{vid}")
    except KickNotFound:
        obj = None
    if isinstance(obj, dict) and obj.get("uuid"):
        item = P.video(obj, languages=languages)
        stream = obj.get("livestream") if isinstance(obj.get("livestream"), dict) else {}
        cid = P.to_int(stream.get("channel_id"))
        web_id = P.text(stream.get("vod_id"))
        if cid and web_id:
            extra = web_optional(f"/channels/{cid}/videos/{web_id}")
            if isinstance(extra, dict):
                _merge(item, _web_extras(extra))
        return {"video": item}
    if channel:
        cid = shared.channel_id(channel)
        extra = web_optional(f"/channels/{cid}/videos/{vid}")
        if isinstance(extra, dict) and extra.get("id"):
            item = P.video(extra, languages=languages)
            return {"video": item}
    raise KickNotFound(f"video '{vid}' not found"
                       + ("" if channel else " (for a new-style video id pass the full "
                                             "https://kick.com/<channel>/videos/<id> link)"))

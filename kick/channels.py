"""/kick/channels/* — one channel's profile, live status, socials, emotes,
gift leaderboards, poll / prediction / goals / channel-point rewards, chat
settings, who is in chat, the live HLS playlist and one viewer's standing in
that chat. Every function takes the resolved `channel` slug."""
from kick import parsers as P
from kick import shared
from kick.fetch import (KickNotFound, gather, legacy, legacy_optional, run_parallel,
                        web, web_optional)


def _not_found(slug):
    return KickNotFound(f"channel '{slug}' not found")


def details(channel):
    """The full channel card. The v1 channel object is the richest spelling
    (it alone carries the subscription price, the name-change date and the
    profile links); the v2 object fills in anything v1 lacks."""
    parts = gather({
        "v1": lambda: legacy(f"/api/v1/channels/{channel}"),
        # the chatroom copy embedded in the channel object is stale (it
        # disagrees with the chat's live settings), so the live one is read
        "room": lambda: legacy(f"/api/v2/channels/{channel}/chatroom"),
        "rules": lambda: legacy(f"/api/v2/channels/{channel}/chatroom/rules"),
    })
    v1 = parts["v1"]
    if not isinstance(v1, dict) or v1.get("id") is None:
        raise _not_found(channel)
    shared.remember(("channel_id", channel), shared.ID_TTL, P.to_int(v1["id"]))
    out = P.channel_details(v1, languages=shared.languages())
    if isinstance(parts["room"], dict):
        rules = ((parts["rules"] or {}).get("data") or {}).get("rules") if isinstance(parts["rules"], dict) else None
        room = P.chatroom(parts["room"], rules=rules or "")
        stale = out.get("chatroom") or {}
        if "mode" in stale:
            room = {"id": room["id"], "mode": stale["mode"], **{k: v for k, v in room.items() if k != "id"}}
        out["chatroom"] = room
    plan = v1.get("plan") if isinstance(v1.get("plan"), dict) else None
    price = P.to_float(plan.get("amount")) if plan else None
    out["subscription"] = {"price": price, "currency": "USD" if price is not None else None}
    out["username_updated_at"] = P.iso_datetime(v1.get("name_updated_at"))
    out["links"] = [P.channel_link_row(r) for r in (v1.get("ascending_links") or []) if isinstance(r, dict)]
    out["created_at"] = P.iso_datetime((v1.get("chatroom") or {}).get("created_at")) \
        if isinstance(v1.get("chatroom"), dict) else None
    order = ["id", "slug", "username", "link", "bio", "profile_image", "banner", "offline_banner",
             "is_live", "is_verified", "is_affiliate", "is_banned", "has_subscriptions_enabled",
             "has_vods_enabled", "followers_count", "subscription", "socials", "links", "livestream",
             "recent_categories", "subscriber_badges", "chatroom", "playback_link", "user_id",
             "created_at", "username_updated_at"]
    return {"channel": {k: out.get(k) for k in order}}


def _status_of(slug):
    try:
        body = legacy(f"/api/v2/channels/{slug}/livestream")
    except KickNotFound:
        raise _not_found(slug)
    data = body.get("data") if isinstance(body, dict) else None
    live = P.without_channel(P.livestream(data, channel=P.channel_ref(None, slug=slug),
                                          languages=shared.languages())) \
        if isinstance(data, dict) else None
    return {
        "channel": slug,
        "link": P.refs.channel_link(slug),
        "is_live": live is not None,
        "livestream": live,
    }


def status(channel):
    """Is the channel live right now, with viewers, uptime, title, category
    and the playback link — one light call, built for polling/alerts."""
    return _status_of(channel)


def status_batch(channels):
    """Live status for up to 25 channels in one call. A slug that does not
    exist yields {"channel", "error": "not found"} instead of failing the
    batch."""
    def one(slug):
        def run():
            try:
                return _status_of(slug)
            except KickNotFound:
                return {"channel": slug, "link": None, "is_live": None, "livestream": None,
                        "error": "not found"}
        return run
    rows = run_parallel([one(s) for s in channels])
    return {
        "live_count": sum(1 for r in rows if r.get("is_live")),
        "count": len(rows),
        "channels": rows,
    }


def links(channel):
    try:
        rows = legacy(f"/api/v2/channels/{channel}/links")
    except KickNotFound:
        raise _not_found(channel)
    items = [P.channel_link_row(r) for r in (rows or []) if isinstance(r, dict)]
    items.sort(key=lambda r: (r["order"] is None, r["order"] or 0))
    return {"channel": channel, "count": len(items), "links": items}


def emotes(channel):
    try:
        payload = legacy(f"/emotes/{channel}")
    except KickNotFound:
        raise _not_found(channel)
    sets = P.emote_sets(payload)
    return {
        "channel": channel,
        "channel_emotes_count": len(sets["channel"]),
        "channel_emotes": sets["channel"],
        "global_emotes": sets["global"],
        "emoji": sets["emoji"],
    }


def recent_categories(channel):
    try:
        rows = legacy(f"/api/v2/channels/{channel}/recent-categories")
    except KickNotFound:
        raise _not_found(channel)
    items = [P.category_ref(r) for r in (rows or []) if isinstance(r, dict)]
    return {"channel": channel, "count": len(items), "categories": items}


def leaderboards(channel):
    """Both gift leaderboards: gifted subscriptions (v2) and Kicks, Kick's
    virtual currency (web) — each all-time / month / week top 10."""
    cid = shared.channel_id(channel)
    parts = gather({
        "subs": lambda: legacy(f"/api/v2/channels/{channel}/leaderboards"),
        "kicks": lambda: web(f"/kicks/{cid}/leaderboard"),
    })
    return {
        "channel": channel,
        "gifted_subscriptions": P.gift_leaderboards(parts["subs"]),
        "kicks": P.kicks_leaderboards(parts["kicks"]),
    }


def poll(channel):
    """The channel's current (or just-finished) chat poll; null when none."""
    try:
        body = legacy(f"/api/v2/channels/{channel}/polls")
    except KickNotFound:
        raise _not_found(channel)
    data = body.get("data") if isinstance(body, dict) else None
    return {"channel": channel, "poll": P.poll((data or {}).get("poll")) if isinstance(data, dict) else None}


def prediction(channel):
    """The channel's latest channel-points prediction (active, locked,
    resolved or cancelled); null when the channel never ran one."""
    body = legacy_optional(f"/api/v2/channels/{channel}/predictions/latest")
    if body is None:
        shared.channel_id(channel)        # 404 for an unknown channel
    data = body.get("data") if isinstance(body, dict) else None
    pred = (data or {}).get("prediction") if isinstance(data, dict) else None
    return {"channel": channel, "prediction": P.prediction(pred)}


def goals(channel):
    try:
        rows = legacy(f"/api/v2/channels/{channel}/goals")
    except KickNotFound:
        raise _not_found(channel)
    items = [P.goal(r) for r in (rows if isinstance(rows, list) else []) if isinstance(r, dict)]
    return {"channel": channel, "count": len(items), "goals": items}


def rewards(channel):
    try:
        body = legacy(f"/api/v2/channels/{channel}/rewards")
    except KickNotFound:
        raise _not_found(channel)
    rows = body.get("data") if isinstance(body, dict) else body
    items = [P.reward(r) for r in (rows if isinstance(rows, list) else []) if isinstance(r, dict)]
    return {"channel": channel, "count": len(items), "rewards": items}


def chatroom(channel):
    """Chat settings (slow / followers-only / subscribers-only / emote-only /
    account-age modes), the channel's chat rules and the pinned message."""
    parts = gather({
        "room": lambda: legacy(f"/api/v2/channels/{channel}/chatroom"),
        "rules": lambda: legacy(f"/api/v2/channels/{channel}/chatroom/rules"),
    })
    if parts["room"] is None:
        raise _not_found(channel)
    rules = ((parts["rules"] or {}).get("data") or {}).get("rules") if isinstance(parts["rules"], dict) else None
    return {"channel": channel, "chatroom": P.chatroom(parts["room"], rules=rules or "")}


def chatters(channel):
    """Who is in chat right now, grouped (moderators, VIPs, OGs, viewers,
    bots). Kick caps the `viewers` group at 100; total_count is the full
    number of chatters."""
    cid = shared.channel_id(channel)
    data = web(f"/channels/{cid}/chat/active-chatters")
    return {"channel": channel, **P.chatters(data)}


def playback(channel):
    """The channel's HLS master playlist (m3u8, signed ~1 h) plus live state.
    Kick issues the playlist even while offline; it only plays when live."""
    parts = gather({
        "url": lambda: legacy(f"/api/v2/channels/{channel}/playback-url"),
        "live": lambda: legacy(f"/api/v2/channels/{channel}/livestream"),
    })
    if parts["url"] is None and parts["live"] is None:
        raise _not_found(channel)
    link = (parts["url"] or {}).get("data") if isinstance(parts["url"], dict) else None
    live = (parts["live"] or {}).get("data") if isinstance(parts["live"], dict) else None
    return {
        "channel": channel,
        "is_live": isinstance(live, dict),
        "playback_link": P.text(link) if isinstance(link, str) else None,
    }


def chat_user(channel, user):
    """One user's standing in a channel's chat: owner / moderator / staff,
    badges (subscriber months, level, founder, ...), how long they have
    followed and been subscribed, and any active ban."""
    try:
        obj = legacy(f"/api/v2/channels/{channel}/users/{user}")
    except KickNotFound:
        # the upstream answers "Channel not found" for a missing user too
        shared.channel_id(channel)
        raise KickNotFound(f"user '{user}' not found")
    return {"channel": channel, "user": P.chat_user_card(obj)}

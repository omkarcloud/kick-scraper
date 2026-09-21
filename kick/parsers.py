"""Kick normalizers: the legacy kick.com/api objects and the newer
web.kick.com objects -> one clean snake_case shape per entity.

Output conventions (shared with the other scrapers here): `link` for
canonical page URLs (always absolute), `image`/`thumbnail`/`banner` for
pictures, `*_count` for counters, `is_*`/`has_*` for booleans, ISO-8601 UTC
("2026-09-21T09:05:54Z") for timestamps, numbers as numbers, null for
missing. Entity refs share one vocabulary:

  channel   {id, slug, username, link, profile_image, is_verified}
  category  {id, name, slug, link, ...}  with `directory` = its parent
            (Games / IRL / Music / ...; Kick's own API calls the browsable
            game/topic pages "subcategories" and the six roots "categories")
  user      {id, username, slug, link, profile_image}

Deliberately dropped as noise: the srcset strings (one canonical link is
kept, plus the 1080p thumbnail where the site ships one), Laravel's
`*_page_url` link farm and `links[]` widgets, `playback_url` on channel
LISTS (kept on details / playback endpoints), `risk_level_id`,
`twitch_channel`, `trading_platform_id`, `s3`/`thumb`/`deleted_at`/
`is_pruned` video bookkeeping, the `agreed_to_terms`/`email_verified_at`/
`gender`/`country`/`state`/`city` fields Kick leaks on embedded user
objects (always null for other users), `chatable_type`/`chatable_id`
(Laravel polymorphism), `can_host`/`role`/`muted`/`following`/
`subscription`/`liked`/`followed`/`selected` (viewer-relative flags that
are meaningless for an anonymous reader), `badges_v2[].selected/sort_order`,
chat `metadata.message_ref` (a client-side dedupe token), the typesense
`text_match*`/`highlight*`/`request_params` scoring blobs and `out_of`.
"""
import json
import re
from datetime import datetime, timezone

from kick import refs

FILES = "https://files.kick.com"
DEFAULT_AVATAR_RE = re.compile(r"/default-profile-pictures/|/default-avatar", re.I)
_SRCSET_RE = re.compile(r"(\S+)\s+(\d+)w")


# ---- value helpers ------------------------------------------------------------
# (kept local so the package stands alone, like the other site packages)

def to_int(value):
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None


def to_float(value):
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def text(value):
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def bool_or_none(value):
    return value if isinstance(value, bool) else None


def iso_datetime(value):
    """Kick's three timestamp spellings -> '2026-09-21T09:05:54Z' (UTC):
    '2026-09-21T09:05:54.000000Z', '2026-09-21 09:05:54' (UTC, no zone) and
    '2026-09-20T20:18:11+00:00'. The zero date '0001-01-01T00:00:00Z' and
    junk -> None."""
    if not value or not isinstance(value, str):
        return None
    raw = value.strip()
    if raw.startswith("0001-"):
        return None
    if " " in raw and "T" not in raw:
        raw = raw.replace(" ", "T", 1)
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def seconds_since(iso):
    """Whole seconds between an ISO timestamp and now (None if unknown)."""
    if not iso:
        return None
    try:
        started = datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return max(int((datetime.now(timezone.utc) - started).total_seconds()), 0)


def duration_text(seconds):
    """41486 -> '11:31:26'; 30 -> '0:30'."""
    seconds = to_int(seconds)
    if seconds is None:
        return None
    hours, rest = divmod(seconds, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{hours}:{minutes:02d}:{secs:02d}" if hours else f"{minutes}:{secs:02d}"


def image_link(value):
    """An image in any of Kick's spellings -> one https link or None.
    Accepts a bare string, {url}, {src, srcset}, {responsive, url}."""
    if isinstance(value, str):
        value = value.strip()
        return value or None
    if isinstance(value, dict):
        for key in ("src", "url", "link"):
            link = text(value.get(key))
            if link:
                return link
    return None


def largest_in_srcset(value):
    """'a.webp 1920w, b.webp 1280w' -> 'a.webp' (the widest candidate)."""
    srcset = value.get("srcset") or value.get("srcSet") if isinstance(value, dict) else value
    if not isinstance(srcset, str):
        return None
    best, best_w = None, -1
    for link, width in _SRCSET_RE.findall(srcset):
        if int(width) > best_w:
            best, best_w = link, int(width)
    return best


def thumbnail(value):
    """A stream/video thumbnail -> {link (720p), hd_link (1080p)} or None."""
    link = image_link(value)
    if not link:
        return None
    hd = largest_in_srcset(value)
    return {"link": link, "hd_link": hd if hd and hd != link else None}


def profile_image(value):
    """A profile picture link; Kick's stock default avatars -> None."""
    link = image_link(value)
    if not link or DEFAULT_AVATAR_RE.search(link):
        return None
    return link


def emote_image(emote_id):
    return f"{FILES}/emotes/{emote_id}/fullsize" if emote_id else None


def language_pair(value, iso=None, languages=None):
    """Kick's legacy rows carry the language NAME ('Polish', sometimes with
    a `lang_iso` sibling); web rows carry the CODE ('pl'). -> (name, code),
    either side filled from `languages` = {"by_name": {name.lower(): code},
    "by_code": {code: name}} (the /stream/languages table) when given."""
    languages = languages or {}
    value = text(value)
    code = text(iso)
    name = None
    if value and re.fullmatch(r"[a-z]{2,3}(-[A-Za-z]{2})?", value):
        code = code or value
    else:
        name = value
    if name and not code:
        code = (languages.get("by_name") or {}).get(name.lower())
    if code and not name:
        name = (languages.get("by_code") or {}).get(code)
    return name, code


# ---- refs ------------------------------------------------------------------------

def channel_ref(obj, *, slug=None):
    """A channel stub in any of its spellings (legacy channel with nested
    user, web {id, slug, username, profile_pic|profile_picture}) ->
    {id, slug, username, link, profile_image, is_verified}."""
    if not isinstance(obj, dict):
        return None if not slug else {"id": None, "slug": slug, "username": None,
                                      "link": refs.channel_link(slug), "profile_image": None,
                                      "is_verified": None}
    user = obj.get("user") if isinstance(obj.get("user"), dict) else {}
    slug = text(obj.get("slug")) or slug
    verified = obj.get("verified")
    if isinstance(verified, dict):
        verified = True
    if verified is None:
        verified = obj.get("is_verified")
    return {
        "id": to_int(obj.get("id")),
        "slug": slug,
        "username": text(obj.get("username")) or text(user.get("username")),
        "link": refs.channel_link(slug),
        "profile_image": profile_image(obj.get("profile_pic") or obj.get("profile_picture")
                                       or user.get("profile_pic") or user.get("profilepic")
                                       or user.get("profilePic")),
        "is_verified": bool_or_none(verified),
    }


def user_ref(obj, *, with_id=True, with_image=True):
    """A chat sender / clip creator / leaderboard row -> {id, username, slug,
    link, profile_image}. `with_id` / `with_image` drop the fields a source
    never carries (chatter lists have no ids, leaderboards no pictures)."""
    if not isinstance(obj, dict):
        return None
    slug = text(obj.get("slug")) or (text(obj.get("username")) or "").lower() or None
    out = {}
    if with_id:
        out["id"] = to_int(obj.get("id") or obj.get("user_id"))
    out.update({"username": text(obj.get("username")), "slug": slug, "link": refs.channel_link(slug)})
    if with_image:
        out["profile_image"] = profile_image(obj.get("profile_pic") or obj.get("profile_picture")
                                             or obj.get("profilepic"))
    return out


def directory_ref(obj):
    """One of the six root categories (Games, IRL, ...) -> {id, name, slug, icon}."""
    if isinstance(obj, str):
        return {"id": None, "name": None, "slug": obj, "icon": None}
    if not isinstance(obj, dict):
        return None
    return {
        "id": to_int(obj.get("id")),
        "name": text(obj.get("name")),
        "slug": text(obj.get("slug")),
        "icon": text(obj.get("icon")),
    }


def category_stub(obj):
    """An embedded category (on a stream, VOD or clip) -> {id, name, slug,
    link}. Full category rows (lists, details, search) use category_ref."""
    if not isinstance(obj, dict):
        return None
    slug = text(obj.get("slug"))
    return {"id": to_int(obj.get("id")), "name": text(obj.get("name")), "slug": slug,
            "link": refs.category_link(slug)}


def category_ref(obj):
    """A category (Kick "subcategory") in any spelling -> the public shape.
    Legacy rows carry banner {url|src, responsive|srcset} + parent
    `category`; web rows just {id, name, slug} (+ parent_category slug on
    clips); typesense docs {src, parent, category_id, is_live}."""
    if not isinstance(obj, dict):
        return None
    slug = text(obj.get("slug"))
    banner = obj.get("banner") or obj.get("thumbnail")
    if not banner and obj.get("src"):
        banner = obj
    parent = obj.get("category") or obj.get("parent_category") or obj.get("parent")
    directory = directory_ref(parent) if parent else None
    if directory and directory.get("id") is None and obj.get("category_id") is not None:
        directory["id"] = to_int(obj.get("category_id"))
    out = {
        "id": to_int(obj.get("id")),
        "name": text(obj.get("name")),
        "slug": slug,
        "link": refs.category_link(slug),
        "description": text(obj.get("description")),
        "tags": [t for t in (obj.get("tags") or []) if isinstance(t, str)],
        "is_mature": bool_or_none(obj.get("is_mature")),
        "is_promoted": bool_or_none(obj.get("is_promoted")),
        "is_live": bool_or_none(obj.get("is_live")),
        "viewer_count": to_int(obj.get("viewers") if obj.get("viewers") is not None else obj.get("viewer_count")),
        "followers_count": to_int(obj.get("followers_count")),
        "banner": image_link(banner) if banner else None,
        "directory": directory,
    }
    return out


# ---- channel ------------------------------------------------------------------------

def socials(user):
    """The user object's social handles -> {platform: link} with Kick's
    partial handles expanded into absolute links (instagram 'xqcow1/' ->
    https://instagram.com/xqcow1)."""
    if not isinstance(user, dict):
        return None
    bases = {
        "instagram": "https://instagram.com/",
        "twitter": "https://x.com/",
        "youtube": "https://youtube.com/",
        "discord": "https://discord.gg/",
        "tiktok": "https://tiktok.com/@",
        "facebook": "https://facebook.com/",
    }
    out = {}
    for platform, base in bases.items():
        handle = text(user.get(platform))
        if not handle:
            out[platform] = None
            continue
        if handle.startswith("http"):
            out[platform] = handle
            continue
        handle = handle.strip("/@ ")
        if platform == "discord" and handle.startswith("invite/"):
            handle = handle[len("invite/"):]
        if platform == "tiktok":
            handle = handle.lstrip("@")
        out[platform] = base + handle
    return out


def subscriber_badges(items):
    out = []
    for badge in items or []:
        if not isinstance(badge, dict):
            continue
        out.append({
            "id": to_int(badge.get("id")),
            "months": to_int(badge.get("months")),
            "image": image_link(badge.get("badge_image")),
        })
    return out


def chatroom(obj, rules=None):
    """The v2 chatroom settings ({slow_mode: {enabled, message_interval}, ...})
    OR the legacy flat chatroom on the channel object -> one shape."""
    if not isinstance(obj, dict):
        return None

    def mode(key, extra=None):
        value = obj.get(key)
        if isinstance(value, dict):
            block = {"is_enabled": bool_or_none(value.get("enabled"))}
            if extra:
                block[extra[0]] = to_int(value.get(extra[1]))
            return block
        block = {"is_enabled": bool_or_none(value)}
        if extra:
            block[extra[0]] = None
        return block

    slow = mode("slow_mode", ("interval_seconds", "message_interval"))
    if slow["interval_seconds"] is None and obj.get("message_interval") is not None:
        slow["interval_seconds"] = to_int(obj.get("message_interval"))
    followers = mode("followers_mode", ("min_follow_minutes", "min_duration"))
    if followers["min_follow_minutes"] is None and obj.get("following_min_duration") is not None:
        followers["min_follow_minutes"] = to_int(obj.get("following_min_duration"))
    out = {"id": to_int(obj.get("id"))}
    if "chat_mode" in obj:
        out["mode"] = text(obj.get("chat_mode"))
    out.update({
        "slow_mode": slow,
        "followers_mode": followers,
        "subscribers_mode": mode("subscribers_mode"),
        "emotes_mode": mode("emotes_mode"),
    })
    # The v2 /chatroom spelling carries these; the flat copy embedded in the
    # channel object does not, so they are only emitted where they exist.
    if "account_age" in obj:
        out["account_age"] = mode("account_age", ("min_account_minutes", "min_duration"))
    if rules is not None:
        out["rules"] = text(rules)
    if "pinned_message" in obj:
        out["pinned_message"] = chat_message(obj.get("pinned_message")) if isinstance(obj.get("pinned_message"), dict) else None
    if "gifts_enabled" in obj:
        out["gifts_leaderboard"] = {
            "all_time": mode("gifts_enabled")["is_enabled"],
            "week": mode("gifts_week_enabled")["is_enabled"],
            "month": mode("gifts_month_enabled")["is_enabled"],
        }
    return out


def livestream(obj, *, channel=None, languages=None):
    """A livestream / stream row in any of Kick's spellings -> one shape.

    Legacy (kick.com): {id, slug, session_title, created_at, start_time,
    viewer_count | viewers, language (NAME), lang_iso, is_mature, tags,
    thumbnail, categories[], channel, duration}.
    v2 /livestream: {id, slug, session_title, created_at, language, viewers,
    category (with parent_category), playback_url, thumbnail}.
    Web: {id (uuid), title, viewer_count, show_view_count, start_time,
    channel, category, language (CODE), tags, thumbnail, is_mature}."""
    if not isinstance(obj, dict):
        return None
    title = text(obj.get("session_title")) or text(obj.get("title"))
    started = iso_datetime(obj.get("start_time")) or iso_datetime(obj.get("created_at"))
    viewer_count = obj.get("viewer_count")
    if viewer_count is None:
        viewer_count = obj.get("viewers")
    language, code = language_pair(obj.get("language"), obj.get("lang_iso"), languages)
    categories = obj.get("categories")
    if not categories and obj.get("category"):
        categories = [obj["category"]]
    category_refs = [category_stub(c) for c in (categories or []) if isinstance(c, dict)]
    channel_obj = obj.get("channel") if isinstance(obj.get("channel"), dict) else channel
    chan = channel_ref(channel_obj) if isinstance(channel_obj, dict) else channel
    if chan is None and obj.get("channel_id") is not None:
        chan = {"id": to_int(obj.get("channel_id")), "slug": None, "username": None,
                "link": None, "profile_image": None, "is_verified": None}
    is_live = obj.get("is_live")
    if is_live is None:
        is_live = True      # the v2 /livestream and web rows only exist while live
    return {
        "id": obj.get("id") if isinstance(obj.get("id"), str) else to_int(obj.get("id")),
        "title": title,
        "link": (chan or {}).get("link"),
        "is_live": bool_or_none(is_live),
        "started_at": started,
        "uptime_seconds": seconds_since(started) if is_live else None,
        "viewer_count": to_int(viewer_count),
        "is_viewer_count_shown": bool_or_none(obj.get("show_view_count")),
        "language": language,
        "language_code": code,
        "is_mature": bool_or_none(obj.get("is_mature")),
        "tags": [t for t in (obj.get("tags") or []) if isinstance(t, str)],
        "thumbnail": thumbnail(obj.get("thumbnail")),
        "category": category_refs[0] if category_refs else None,
        "channel": chan,
        "playback_link": text(obj.get("playback_url")),
    }


def without_channel(item):
    """Drop the embedded channel ref where the response is already about
    that one channel (status, details, a channel's own VOD / clip list)."""
    if isinstance(item, dict):
        item.pop("channel", None)
    return item


def channel_details(obj, *, languages=None):
    """The v2 channel object -> the public channel card."""
    if not isinstance(obj, dict):
        return None
    slug = text(obj.get("slug"))
    user = obj.get("user") if isinstance(obj.get("user"), dict) else {}
    followers = obj.get("followers_count")
    if followers is None:
        followers = obj.get("followersCount")
    live = obj.get("livestream") if isinstance(obj.get("livestream"), dict) else None
    verified = obj.get("verified")
    if isinstance(verified, dict):
        verified = True
    return {
        "id": to_int(obj.get("id")),
        "slug": slug,
        "username": text(user.get("username")),
        "link": refs.channel_link(slug),
        "bio": text(user.get("bio")),
        "profile_image": profile_image(user.get("profile_pic") or user.get("profilepic")),
        "banner": image_link(obj.get("banner_image")),
        "offline_banner": image_link(obj.get("offline_banner_image")),
        "is_live": live is not None,
        "is_verified": bool_or_none(verified),
        "is_affiliate": bool_or_none(obj.get("is_affiliate")),
        "is_banned": bool_or_none(obj.get("is_banned")),
        "has_subscriptions_enabled": bool_or_none(obj.get("subscription_enabled")),
        "has_vods_enabled": bool_or_none(obj.get("vod_enabled")),
        "followers_count": to_int(followers),
        "user_id": to_int(user.get("id") or obj.get("user_id")),
        "socials": socials(user),
        "livestream": without_channel(livestream(live, channel=channel_ref(None, slug=slug),
                                                 languages=languages)) if live else None,
        "recent_categories": [category_ref(c) for c in (obj.get("recent_categories") or [])
                              if isinstance(c, dict)],
        "subscriber_badges": subscriber_badges(obj.get("subscriber_badges")),
        "chatroom": chatroom(obj.get("chatroom")) if isinstance(obj.get("chatroom"), dict) else None,
        "playback_link": text(obj.get("playback_url")),
    }


def user_profile(obj):
    """/api/v1/users/{slug} -> {id, username, bio, profile_image, socials}."""
    if not isinstance(obj, dict):
        return None
    return {
        "id": to_int(obj.get("id")),
        "username": text(obj.get("username")),
        "bio": text(obj.get("bio")),
        "profile_image": profile_image(obj.get("profilepic") or obj.get("profile_pic")),
        "socials": socials(obj),
    }


def channel_link_row(obj):
    if not isinstance(obj, dict):
        return None
    return {
        "id": to_int(obj.get("id")),
        "title": text(obj.get("title")),
        "description": text(obj.get("description")),
        "link": text(obj.get("link")),
        "image": image_link(obj.get("image")),
        "order": to_int(obj.get("order")),
        "created_at": iso_datetime(obj.get("created_at")),
        "updated_at": iso_datetime(obj.get("updated_at")),
    }


def emote(obj):
    if not isinstance(obj, dict):
        return None
    emote_id = to_int(obj.get("id"))
    return {
        "id": emote_id,
        "name": text(obj.get("name")),
        "image": emote_image(emote_id),
        "is_subscribers_only": bool_or_none(obj.get("subscribers_only")),
    }


def emote_sets(payload):
    """/emotes/{slug} -> {channel: [...], global: [...], emoji: [...]}.
    The payload is a list of three sets: the channel's own (a channel
    object carrying `emotes`), "Global" and "Emojis"."""
    out = {"channel": [], "global": [], "emoji": []}
    for item in payload if isinstance(payload, list) else []:
        if not isinstance(item, dict):
            continue
        emotes = [emote(e) for e in (item.get("emotes") or []) if isinstance(e, dict)]
        name = str(item.get("id") or item.get("name") or "")
        if name.lower() == "global":
            out["global"] = emotes
        elif name.lower() in ("emoji", "emojis"):
            out["emoji"] = emotes
        else:
            out["channel"] = emotes
    return out


def leaderboard_rows(items):
    out = []
    for rank, row in enumerate(items or [], start=1):
        if not isinstance(row, dict):
            continue
        out.append({"rank": rank, "user": user_ref(row, with_image=False), "quantity": to_int(row.get("quantity"))})
    return out


def gift_leaderboards(obj):
    """v2 leaderboards ({gifts, gifts_week, gifts_month, *_enabled}) ->
    {all_time, month, week} each {is_enabled, rows}."""
    if not isinstance(obj, dict):
        return None
    return {
        "all_time": {"is_enabled": bool_or_none(obj.get("gifts_enabled")),
                     "rows": leaderboard_rows(obj.get("gifts"))},
        "month": {"is_enabled": bool_or_none(obj.get("gifts_month_enabled")),
                  "rows": leaderboard_rows(obj.get("gifts_month"))},
        "week": {"is_enabled": bool_or_none(obj.get("gifts_week_enabled")),
                 "rows": leaderboard_rows(obj.get("gifts_week"))},
    }


def kicks_leaderboards(obj):
    """web kicks/{id}/leaderboard data -> same shape as gift_leaderboards."""
    if not isinstance(obj, dict):
        return None
    return {
        "all_time": {"is_enabled": bool_or_none(obj.get("kicks_gifts_lifetime_enabled")),
                     "rows": leaderboard_rows(obj.get("kicks_gifts_lifetime"))},
        "month": {"is_enabled": bool_or_none(obj.get("kicks_gifts_month_enabled")),
                  "rows": leaderboard_rows(obj.get("kicks_gifts_month"))},
        "week": {"is_enabled": bool_or_none(obj.get("kicks_gifts_week_enabled")),
                 "rows": leaderboard_rows(obj.get("kicks_gifts_week"))},
    }


def poll(obj):
    """v2 polls data.poll -> {title, options[], duration_seconds, ...}."""
    if not isinstance(obj, dict):
        return None
    options = []
    for option in obj.get("options") or []:
        if isinstance(option, dict):
            options.append({"id": to_int(option.get("id")), "label": text(option.get("label")),
                            "votes_count": to_int(option.get("votes"))})
    total = sum(o["votes_count"] or 0 for o in options)
    for option in options:
        option["votes_percent"] = round((option["votes_count"] or 0) * 100 / total, 1) if total else 0.0
    remaining = to_int(obj.get("remaining"))
    return {
        "title": text(obj.get("title")),
        "is_active": remaining > 0 if remaining is not None else None,
        "votes_count": total,
        "options": options,
        "duration_seconds": to_int(obj.get("duration")),
        "remaining_seconds": remaining,
        "result_display_seconds": to_int(obj.get("result_display_duration")),
        "created_at": iso_datetime(obj.get("created_at")),
    }


def prediction(obj):
    if not isinstance(obj, dict):
        return None
    outcomes = []
    for outcome in obj.get("outcomes") or []:
        if not isinstance(outcome, dict):
            continue
        outcomes.append({
            "id": text(outcome.get("id")),
            "title": text(outcome.get("title")),
            "is_winner": (text(outcome.get("id")) == text(obj.get("winning_outcome_id")))
            if obj.get("winning_outcome_id") else None,
            "votes_count": to_int(outcome.get("vote_count")),
            "points_total": to_int(outcome.get("total_vote_amount")),
            "return_rate": to_float(outcome.get("return_rate")),
            "top_users": [{"user": user_ref(u, with_image=False), "points": to_int(u.get("amount"))}
                          for u in (outcome.get("top_users") or []) if isinstance(u, dict)],
        })
    return {
        "id": text(obj.get("id")),
        "title": text(obj.get("title")),
        "state": text(obj.get("state")),
        "duration_seconds": to_int(obj.get("duration")),
        "created_at": iso_datetime(obj.get("created_at")),
        "locked_at": iso_datetime(obj.get("locked_at")),
        "updated_at": iso_datetime(obj.get("updated_at")),
        "winning_outcome_id": text(obj.get("winning_outcome_id")),
        "outcomes": outcomes,
    }


def goal(obj):
    """v2 goals row: {id 'chgoal_…', type subscriptions|followers|…, status,
    target_value, current_value, end_date, achieved_at, created_at,
    updated_at, count_from_creation}."""
    if not isinstance(obj, dict):
        return None
    current, target = to_int(obj.get("current_value")), to_int(obj.get("target_value"))
    return {
        "id": text(obj.get("id")) if isinstance(obj.get("id"), str) else to_int(obj.get("id")),
        "type": text(obj.get("type")),
        "status": text(obj.get("status")),
        "current": current,
        "target": target,
        "progress_percent": round(current * 100 / target, 1) if current is not None and target else None,
        "is_counted_from_creation": bool_or_none(obj.get("count_from_creation")),
        "ends_at": iso_datetime(obj.get("end_date")),
        "achieved_at": iso_datetime(obj.get("achieved_at")),
        "created_at": iso_datetime(obj.get("created_at")),
        "updated_at": iso_datetime(obj.get("updated_at")),
    }


def reward(obj):
    """v2 channel-points reward."""
    if not isinstance(obj, dict):
        return None
    return {
        "id": text(obj.get("id")) if isinstance(obj.get("id"), str) else to_int(obj.get("id")),
        "title": text(obj.get("title")),
        "description": text(obj.get("description")),
        "cost": to_int(obj.get("cost")),
        "background_color": text(obj.get("background_color")),
        "is_enabled": bool_or_none(obj.get("is_enabled")),
        "is_paused": bool_or_none(obj.get("is_paused")),
        "is_user_input_required": bool_or_none(obj.get("is_user_input_required")),
        "prompt": text(obj.get("prompt")),
        "skips_request_queue": bool_or_none(obj.get("should_redemptions_skip_request_queue")),
    }


def event(obj):
    if not isinstance(obj, dict):
        return None
    return {
        "id": text(obj.get("id")),
        "title": text(obj.get("title")),
        "description": text(obj.get("description")),
        "starts_at": iso_datetime(obj.get("start_time") or obj.get("starts_at")),
        "ends_at": iso_datetime(obj.get("end_time") or obj.get("ends_at")),
        "category": category_ref(obj.get("category")) if isinstance(obj.get("category"), dict) else None,
        "image": image_link(obj.get("image") or obj.get("thumbnail")),
    }


# ---- chat --------------------------------------------------------------------------

def _badges(identity):
    """identity.badges (role badges) + badges_v2 (image badges) -> one list
    of {type, label, image, level}."""
    out = []
    seen = set()
    for badge in (identity or {}).get("badges") or []:
        if not isinstance(badge, dict):
            continue
        kind = text(badge.get("type"))
        out.append({"type": kind, "label": text(badge.get("text")), "image": None,
                    "months": to_int(badge.get("count")), "level": None})
        seen.add(kind)
    for badge in (identity or {}).get("badges_v2") or []:
        if not isinstance(badge, dict):
            continue
        meta = badge.get("metadata") if isinstance(badge.get("metadata"), dict) else {}
        kind = text(badge.get("name"))
        if kind in seen and not badge.get("image_url"):
            continue
        out.append({"type": kind, "label": None,
                    "image": text(badge.get("image_url")),
                    "months": to_int(meta.get("months")), "level": to_int(meta.get("level"))})
    return out


_EMOTE_RE = re.compile(r"\[emote:(\d+):([^\]]*)\]")


def message_emotes(content):
    """'[emote:4147900:catKISS] hi' -> [{id, name, image}] (deduped)."""
    out, seen = [], set()
    for emote_id, name in _EMOTE_RE.findall(content or ""):
        if emote_id in seen:
            continue
        seen.add(emote_id)
        out.append({"id": to_int(emote_id), "name": name or None, "image": emote_image(emote_id)})
    return out


def chat_sender(obj):
    if not isinstance(obj, dict):
        return None
    identity = obj.get("identity") if isinstance(obj.get("identity"), dict) else {}
    out = user_ref(obj, with_image=False)      # chat payloads never carry a picture
    out["color"] = text(identity.get("color"))
    out["badges"] = _badges(identity)
    return out


def chat_message(obj):
    if not isinstance(obj, dict):
        return None
    meta = obj.get("metadata")
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except ValueError:
            meta = {}
    meta = meta if isinstance(meta, dict) else {}
    original = meta.get("original_message") if isinstance(meta.get("original_message"), dict) else None
    reply_to = None
    if original:
        sender = meta.get("original_sender") if isinstance(meta.get("original_sender"), dict) else original.get("sender")
        reply_to = {
            "message_id": text(original.get("id")),
            "content": text(original.get("content")),
            "created_at": iso_datetime(original.get("created_at")),
            "sender": chat_sender(sender),
        }
    content = text(obj.get("content")) if isinstance(obj.get("content"), str) else None
    return {
        "id": text(obj.get("id")),
        "type": text(obj.get("type")),
        "content": content,
        "text": _EMOTE_RE.sub(lambda m: m.group(2), content).strip() or None if content else None,
        "emotes": message_emotes(content),
        "created_at": iso_datetime(obj.get("created_at")),
        "sender": chat_sender(obj.get("sender")),
        "reply_to": reply_to,
        "thread_id": text(obj.get("thread_parent_id")),
        "celebration": meta.get("celebration") if isinstance(meta.get("celebration"), dict) else None,
    }


def chat_history(data):
    """v2 messages data -> {messages, pinned_message, next_cursor}."""
    data = data if isinstance(data, dict) else {}
    messages = [chat_message(m) for m in (data.get("messages") or []) if isinstance(m, dict)]
    pinned = data.get("pinned_message")
    pinned_out = None
    if isinstance(pinned, dict):
        inner = pinned.get("message") if isinstance(pinned.get("message"), dict) else pinned
        pinned_out = chat_message(inner)
        if pinned_out is not None:
            pinned_out["pinned_by"] = user_ref(pinned.get("pinned_by")) if isinstance(pinned.get("pinned_by"), dict) else None
            pinned_out["pinned_duration_seconds"] = to_int(pinned.get("duration"))
    cursor = data.get("cursor")
    return {
        "messages": messages,
        "pinned_message": pinned_out,
        "next_cursor": str(cursor) if cursor not in (None, "", 0) and messages else None,
    }


def chatters(data):
    data = data if isinstance(data, dict) else {}
    groups = {}
    for key in ("moderators", "vips", "ogs", "chatters", "bots"):
        groups[key] = [user_ref(u, with_id=False) for u in (data.get(key) or []) if isinstance(u, dict)]
    return {
        "total_count": to_int(data.get("total_count")),
        "moderators": groups["moderators"],
        "vips": groups["vips"],
        "ogs": groups["ogs"],
        "viewers": groups["chatters"],
        "bots": groups["bots"],
    }


def chat_user_card(obj):
    """v2 channels/{slug}/users/{username} -> the user's standing in that chat."""
    if not isinstance(obj, dict):
        return None
    out = user_ref(obj)
    banned = obj.get("banned") if isinstance(obj.get("banned"), dict) else None
    out.update({
        "is_channel_owner": bool_or_none(obj.get("is_channel_owner")),
        "is_moderator": bool_or_none(obj.get("is_moderator")),
        "is_staff": bool_or_none(obj.get("is_staff")),
        "is_banned": banned is not None,
        "ban": {"reason": text(banned.get("reason")), "is_permanent": bool_or_none(banned.get("permanent")),
                "expires_at": iso_datetime(banned.get("expires_at")),
                "created_at": iso_datetime(banned.get("created_at"))} if banned else None,
        "badges": _badges({"badges": obj.get("badges"), "badges_v2": obj.get("badges_v2")}),
        "following_since": iso_datetime(obj.get("following_since")),
        "subscribed_for_months": to_int(obj.get("subscribed_for")),
        "created_at": iso_datetime(obj.get("created_at")),
    })
    return out


# ---- videos ---------------------------------------------------------------------------

def _duration_seconds(value, is_ms):
    """Legacy rows carry ms (41486000), web rows seconds (41486), live rows 0.
    The unit comes from the spelling, not the magnitude: a short legacy VOD
    (under ~17 min = < 1,000,000 ms) must not be read as seconds."""
    value = to_int(value)
    if value is None:
        return None
    return value // 1000 if is_ms else value


def video(obj, *, channel=None, languages=None):
    """A VOD in the legacy list spelling (livestream row + nested `video`),
    the v1 /video/{uuid} spelling (video + nested `livestream`) or the web
    spelling -> one shape."""
    if not isinstance(obj, dict):
        return None
    # unwrap the two nestings into (stream row, video record)
    if isinstance(obj.get("livestream"), dict) and obj.get("uuid"):
        stream, record = obj["livestream"], obj
    elif isinstance(obj.get("video"), dict):
        stream, record = obj, obj["video"]
    else:
        stream, record = obj, {}
    chan = channel_ref(stream.get("channel")) if isinstance(stream.get("channel"), dict) else channel
    if chan is None and stream.get("channel_id") is not None:
        chan = {"id": to_int(stream.get("channel_id")), "slug": None, "username": None,
                "link": None, "profile_image": None, "is_verified": None}
    slug = (chan or {}).get("slug")
    video_id = text(record.get("uuid")) or (text(stream.get("id")) if isinstance(stream.get("id"), str) else None)
    language, code = language_pair(stream.get("language"), stream.get("lang_iso"), languages)
    categories = stream.get("categories")
    if not categories and stream.get("category"):
        categories = [stream["category"]]
    category_refs = [category_stub(c) for c in (categories or []) if isinstance(c, dict)]
    started = iso_datetime(stream.get("start_time")) or iso_datetime(stream.get("created_at"))
    # legacy spellings (integer livestream id) carry ms, the web one (uuid id) seconds
    duration = _duration_seconds(stream.get("duration"), not isinstance(stream.get("id"), str))
    views = record.get("views")
    if views is None:
        views = stream.get("views")
    thumb = stream.get("thumbnail")
    return {
        "id": video_id,
        "livestream_id": to_int(stream.get("id")) if not isinstance(stream.get("id"), str) else to_int(record.get("live_stream_id")),
        "title": text(stream.get("session_title")) or text(stream.get("title")),
        "link": refs.video_link(slug, text(stream.get("vod_id")) or video_id),
        # a bare-string thumbnail is a presigned S3 URL that expires in 5 min: useless to a caller
        "thumbnail": thumbnail(thumb) if isinstance(thumb, dict) else (
            {"link": thumb, "hd_link": None} if text(thumb) and "X-Amz-" not in thumb else None),
        "duration_seconds": duration,
        "duration": duration_text(duration),
        "views_count": to_int(views),
        "peak_viewer_count": to_int(stream.get("viewer_count")),
        "language": language,
        "language_code": code,
        "is_mature": bool_or_none(stream.get("is_mature")),
        "is_live": bool_or_none(stream.get("is_live")),
        "started_at": started,
        "ended_at": iso_datetime(stream.get("end_time")),
        "created_at": iso_datetime(record.get("created_at")) or iso_datetime(stream.get("created_at")),
        "expires_at": iso_datetime(stream.get("original_expires_at")),
        "privacy": text(record.get("status")) or text(stream.get("status")),
        "is_private": bool_or_none(record.get("is_private")),
        "tags": [t for t in (stream.get("tags") or []) if isinstance(t, str)],
        "category": category_refs[0] if category_refs else None,
        "channel": chan,
        "playback_link": text(record.get("source")) or text(stream.get("source")) or text(stream.get("recording_url")),
    }


def clip(obj):
    """A clip in the v2 spelling (clip_url, view_count, likes_count, category
    with banner, creator with profile picture) or the web spelling
    (playback_url, views_count) -> one shape."""
    if not isinstance(obj, dict):
        return None
    chan = channel_ref(obj.get("channel")) if isinstance(obj.get("channel"), dict) else None
    if chan is None and obj.get("channel_id") is not None:
        chan = {"id": to_int(obj.get("channel_id")), "slug": None, "username": None,
                "link": None, "profile_image": None, "is_verified": None}
    views = obj.get("view_count")
    if views is None:
        views = obj.get("views_count", obj.get("views"))
    likes = obj.get("likes_count")
    if likes is None:
        likes = obj.get("likes")
    clip_id = text(obj.get("id"))
    duration = to_int(obj.get("duration"))
    return {
        "id": clip_id,
        "title": text(obj.get("title")),
        "link": refs.clip_link((chan or {}).get("slug"), clip_id),
        "thumbnail": text(obj.get("thumbnail_url")),
        "playback_link": text(obj.get("clip_url")) or text(obj.get("playback_url")) or text(obj.get("video_url")),
        "duration_seconds": duration,
        "duration": duration_text(duration),
        "views_count": to_int(views),
        "likes_count": to_int(likes),
        "is_mature": bool_or_none(obj.get("is_mature")),
        "privacy": text(obj.get("privacy")),
        "created_at": iso_datetime(obj.get("created_at")),
        "clipped_at": iso_datetime(obj.get("started_at")),
        "vod_offset_seconds": to_int(obj.get("vod_starts_at")),
        "livestream_id": to_int(obj.get("livestream_id")),
        "category": category_stub(obj.get("category")) if isinstance(obj.get("category"), dict) else None,
        "creator": user_ref(obj.get("creator")) if isinstance(obj.get("creator"), dict) else None,
        "channel": chan,
    }


def clip_cursor(value):
    """v2 nextCursor is a JSON string ('{"view":70193,"id":"clip_..."}'),
    web cursor is base64; both are passed back verbatim as opaque tokens."""
    if value in (None, "", 0, "0"):
        return None
    return value if isinstance(value, str) else json.dumps(value)


# ---- pagination -------------------------------------------------------------------------

def laravel_pagination(payload, page, per_page):
    """Laravel paginator fields -> the route_glue pagination block."""
    payload = payload if isinstance(payload, dict) else {}
    total = to_int(payload.get("total"))
    last_page = to_int(payload.get("last_page"))
    per = to_int(payload.get("per_page")) or per_page
    if last_page is None and total is not None and per:
        last_page = max((total + per - 1) // per, 1)
    return {
        "page": to_int(payload.get("current_page")) or page,
        "items_per_page": per,
        "total_pages": last_page,
        "total_count": total,
    }


# ---- search --------------------------------------------------------------------------------

def typesense_channel(doc):
    if not isinstance(doc, dict):
        return None
    slug = text(doc.get("slug"))
    return {
        "id": to_int(doc.get("id")),
        "slug": slug,
        "username": text(doc.get("username")),
        "link": refs.channel_link(slug),
        "is_live": bool_or_none(doc.get("is_live")),
        "is_verified": bool_or_none(doc.get("verified")),
        "is_banned": bool_or_none(doc.get("is_banned")),
        "followers_count": to_int(doc.get("followers_count")),
    }


def search_channel(obj):
    """search.kick.com enriched channel row -> channel ref + live/followers."""
    if not isinstance(obj, dict):
        return None
    out = channel_ref(obj)
    out["is_live"] = bool_or_none(obj.get("is_live"))
    out["followers_count"] = to_int(obj.get("follower_count") if obj.get("follower_count") is not None
                                    else obj.get("followers_count", obj.get("followersCount")))
    return out

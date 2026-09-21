"""The 31 Kick endpoints. Every path is served with and without the `/kick`
prefix, so code generated against the hosted API on RapidAPI (paths like
/channels/details) runs unchanged against this server.

Params are validated by the marshmallow schemas in kick/schemas.py (the same
ones the hosted API uses): ONE param per input — `channel` and `user` take a
slug or a kick.com link, `category` a slug or link, `clip` a clip id or link,
`video` a video id or link. Unknown params are rejected with a 400 so typos
surface.

Two pagination styles, matching what Kick itself allows: page-numbered lists
(categories, channel and category search) page with `page` + `limit`
(count / total_pages / next / previous in the response); cursor lists (live
streams, chat, clips) page with `cursor` (`next_cursor` in the response)."""
import json
from urllib.parse import urlencode

from bottle import request, response, route

from kick import browse, categories, channels, chat, clips, search, videos
from kick import schemas as S
from schema_fields import load_query
from scraper_errors import BadRequest, NotFound


def json_response(data, status=200):
    response.status = status
    response.content_type = "application/json"
    return json.dumps(data, ensure_ascii=False)


def query_dict():
    """The query as unicode strings (bottle 0.12's .get() hands back latin-1
    decoded bytes, so a UTF-8 "Café" would arrive as "CafÃ©")."""
    return {key: request.query.getunicode(key) for key in request.query.keys()}


def _page_link(params, page):
    if not page:
        return None
    query = {k: v for k, v in params.items() if v not in (None, "")}
    query["page"] = page
    return f"{request.urlparts.scheme}://{request.urlparts.netloc}{request.path}?{urlencode(query)}"


def paginate(result, params):
    """Lift the scraper's `pagination` block into the flat shape the hosted
    API returns: count / per_page / current_page / total_pages / next /
    previous first, then the data."""
    pagination = result.pop("pagination", None) or {}
    result.pop("count", None)
    page = int(pagination.get("page") or params.get("page") or 1)
    total_pages = int(pagination.get("total_pages") or 0)
    out = {
        "count": pagination.get("total_count"),
        "per_page": pagination.get("items_per_page"),
        "current_page": page,
        "total_pages": total_pages,
        "next": _page_link(params, page + 1 if page < total_pages else None),
        "previous": _page_link(params, page - 1 if page > 1 else None),
    }
    out.update(result)
    return out


def call(label, schema, fn, paginated=False):
    """Validate the query, run the scraper, map errors: bad params -> 400,
    missing entity -> 404, transport/blocks -> 500."""
    params = query_dict()
    data, error = load_query(schema, params)
    if error:
        return json_response(error, 400)
    try:
        result = fn(**data)
    except ValueError as e:                # bad id / params
        return json_response({"error": str(e)}, 400)
    except BadRequest as e:                # upstream rejected the request
        return json_response({"error": f"kick rejected the request: {e}"}, 400)
    except NotFound as e:
        return json_response({"error": str(e) or "not found"}, 404)
    except Exception as e:                 # retries exhausted / blocked
        return json_response({"error": f"kick {label} failed: {e}"}, 500)
    return json_response(paginate(result, params) if paginated else result)


def mount(path, schema, fn, paginated=False):
    """Serve an endpoint at /path and /kick/path."""
    def handler():
        return call(path.strip("/"), schema, fn, paginated)
    handler.__name__ = "kick_" + path.strip("/").replace("/", "_").replace("-", "_")
    route(path, method="GET")(handler)
    route("/kick" + path, method="GET")(handler)


P = True   # paginated (page + limit)
ENDPOINTS = [
    ("/channels/details", S.ChannelSchema, channels.details, False),
    ("/channels/status", S.ChannelSchema, channels.status, False),
    ("/channels/status/batch", S.ChannelsSchema, channels.status_batch, False),
    ("/search", S.SearchSchema, search.search, False),
    ("/search/channels", S.SearchChannelsSchema, search.channels, P),
    ("/search/categories", S.SearchCategoriesSchema, search.categories, P),
    ("/livestreams", S.LivestreamsSchema, browse.livestreams, False),
    ("/livestreams/featured", S.FeaturedSchema, browse.featured, False),
    ("/livestreams/languages", S.EmptySchema, browse.languages, False),
    ("/chat/messages", S.ChatMessagesSchema, chat.messages, False),
    ("/channels/chatters", S.ChannelSchema, channels.chatters, False),
    ("/channels/chat-user", S.ChatUserSchema, channels.chat_user, False),
    ("/channels/chatroom", S.ChannelSchema, channels.chatroom, False),
    ("/channels/leaderboards", S.ChannelSchema, channels.leaderboards, False),
    ("/channels/prediction", S.ChannelSchema, channels.prediction, False),
    ("/channels/poll", S.ChannelSchema, channels.poll, False),
    ("/channels/goals", S.ChannelSchema, channels.goals, False),
    ("/channels/rewards", S.ChannelSchema, channels.rewards, False),
    ("/channels/emotes", S.ChannelSchema, channels.emotes, False),
    ("/channels/links", S.ChannelSchema, channels.links, False),
    ("/channels/recent-categories", S.ChannelSchema, channels.recent_categories, False),
    ("/channels/playback", S.ChannelSchema, channels.playback, False),
    ("/videos", S.ChannelSchema, videos.channel_videos, False),
    ("/videos/details", S.VideoSchema, videos.details, False),
    ("/clips", S.ChannelClipsSchema, clips.channel_clips, False),
    ("/clips/details", S.ClipSchema, clips.details, False),
    ("/clips/top", S.TopClipsSchema, clips.top_clips, False),
    ("/clips/category", S.CategoryClipsSchema, clips.category_clips, False),
    ("/categories", S.CategoriesSchema, categories.browse, P),
    ("/categories/details", S.CategorySchema, categories.details, False),
    ("/categories/directories", S.EmptySchema, categories.directories, False),
]

for _path, _schema, _fn, _paginated in ENDPOINTS:
    mount(_path, _schema, _fn, _paginated)


@route("/", method="GET")
@route("/health", method="GET")
def health():
    return json_response({"status": "ok", "endpoints": [p for p, *_ in ENDPOINTS]})

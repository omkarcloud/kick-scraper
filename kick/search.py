"""/kick/search* — the site's own search box (channels + categories + live
streams in one call, search.kick.com) and the two Typesense collections
behind it for deeper, filterable, paged lookups (channels by live state or
follower count, categories)."""
from kick import parsers as P
from kick import shared
from kick.fetch import search_api, typesense


def search(query):
    """What the kick.com search box shows: top channels, categories and
    live streams for a query."""
    data = search_api("/search/enriched", {"query": query}) or {}
    table = shared.languages()
    channels = [P.search_channel(c) for c in (data.get("channels") or []) if isinstance(c, dict)]
    categories = [P.category_ref(c) for c in (data.get("categories") or []) if isinstance(c, dict)]
    livestreams = [P.livestream(r, languages=table) for r in (data.get("livestreams") or []) if isinstance(r, dict)]
    return {"query": query, "channels": channels, "categories": categories, "livestreams": livestreams}


def _pagination(body, page, limit):
    found = P.to_int(body.get("found")) or 0
    return {"page": page, "items_per_page": limit,
            "total_pages": (found + limit - 1) // limit if found else 0,
            "total_count": found}


def channels(query, is_live=None, sort="relevance", page=1, limit=20):
    params = {"q": query, "query_by": "username", "page": page, "per_page": limit}
    if is_live is not None:
        params["filter_by"] = f"is_live:={'true' if is_live else 'false'}"
    if sort == "followers":
        params["sort_by"] = "followers_count:desc"
    body = typesense("channel", params) or {}
    rows = [P.typesense_channel(h.get("document")) for h in (body.get("hits") or []) if isinstance(h, dict)]
    return {"query": query, "pagination": _pagination(body, page, limit), "channels": rows}


def categories(query, is_live=None, page=1, limit=20):
    params = {"q": query, "query_by": "name", "page": page, "per_page": limit}
    if is_live is not None:
        params["filter_by"] = f"is_live:={'true' if is_live else 'false'}"
    body = typesense("subcategory_index", params) or {}
    rows = [P.category_ref(h.get("document")) for h in (body.get("hits") or []) if isinstance(h, dict)]
    return {"query": query, "pagination": _pagination(body, page, limit), "categories": rows}

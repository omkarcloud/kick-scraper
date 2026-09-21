"""/kick/livestreams* — the live directory (web.kick.com): every live stream
on Kick, sortable by viewers, filterable by language(s), category,
directory (Games / IRL / ...) and tag, cursor-paged up to 100 per call;
the featured shelf of the homepage; and the language table."""
from kick import parsers as P
from kick import shared
from kick.fetch import web

SORTS = {"viewers_desc": "viewer_count_desc", "viewers_asc": "viewer_count_asc",
         "featured": "featured"}


def livestreams(sort="viewers_desc", languages=None, category=None, directory=None,
                tag=None, limit=24, cursor=None):
    params = {
        "sort": SORTS.get(sort, sort),
        "limit": limit,
        "language": languages or None,          # repeated key: language=en&language=es
        "category_id": shared.category_id(category) if category else None,
        "directory_id": shared.directory_id(directory) if directory else None,
        # the upstream tag match is exact and Kick stores tags lower-cased
        "tag": tag.lower() if tag else None,
        "after": cursor,
    }
    data = web("/livestreams", params) or {}
    table = shared.languages()
    rows = [P.livestream(r, languages=table) for r in (data.get("livestreams") or []) if isinstance(r, dict)]
    pagination = data.get("pagination") if isinstance(data.get("pagination"), dict) else {}
    return {
        "sort": sort,
        "count": len(rows),
        "next_cursor": P.text(pagination.get("next_cursor")) if rows and len(rows) >= limit else None,
        "previous_cursor": P.text(pagination.get("prev_cursor")),
        "livestreams": rows,
    }


def featured(language="en"):
    """The homepage's featured carousel for one language (~14 streams)."""
    data = web("/livestreams/featured", {"language": language}) or {}
    table = shared.languages()
    rows = [P.livestream(r, languages=table) for r in (data.get("livestreams") or []) if isinstance(r, dict)]
    return {"language": language, "count": len(rows), "livestreams": rows}


def languages():
    """Every stream language Kick knows [{code, name, has_live_filter}] —
    `code` is what /kick/livestreams?languages= takes."""
    table = shared.languages()
    live = set(table["live_codes"])
    rows = [{"code": r["code"], "name": r["name"], "has_live_filter": r["code"] in live}
            for r in table["list"]]
    known = {r["code"] for r in rows}
    rows += [{"code": c, "name": None, "has_live_filter": True} for c in table["live_codes"] if c not in known]
    return {"count": len(rows), "languages": rows}

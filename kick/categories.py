"""/kick/categories* — Kick's catalogue: six root directories (Games, IRL,
Music, Gambling, Creative, Alternative) holding ~13k categories (games and
topics — "subcategories" in Kick's own API), sorted by live viewers."""
from kick import parsers as P
from kick import shared
from kick.fetch import legacy


def directories():
    rows = shared.directories()
    return {"count": len(rows), "directories": rows}


def browse(directory=None, page=1, limit=24):
    """Categories by current viewers (most watched first), optionally inside
    one directory. Page-numbered (flat pagination block)."""
    body = legacy("/api/v1/subcategories", {"page": page, "limit": limit, "category": directory}) or {}
    rows = [P.category_ref(r) for r in (body.get("data") or []) if isinstance(r, dict)]
    return {
        "directory": directory,
        "pagination": P.laravel_pagination(body, page, limit),
        "categories": rows,
    }


def details(category):
    obj = shared.category_raw(category)
    return {"category": P.category_ref(obj)}

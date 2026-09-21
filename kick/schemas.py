"""Marshmallow request schemas for every /kick/* route. Generic fields come
from the shared schema_fields.py; this module adds the Kick resolvers.
Every schema's load() output is the kwargs dict its endpoint function takes.

ONE param per input (tripadvisor QueryOrIdField convention, never a sibling
`url`/`id` pair):

    channel    a channel slug (xqc) OR any kick.com channel link
    channels   comma-separated slugs and/or links (max 25)
    user       a username/slug OR a kick.com profile link
    category   a category slug (just-chatting) OR a kick.com category link
    clip       a clip id (clip_01H8...) OR a kick.com clip link
    video      a video id (uuid) OR a kick.com video link
"""
import re
from datetime import datetime, timezone

from marshmallow import ValidationError, fields, validates_schema

from schema_fields import (BaseSchema, ChoiceField, Flag, LimitField, PageField,
                           QueryField, RefField, StrippedString)
from kick import refs

DIRECTORIES = ["games", "irl", "music", "gambling", "creative", "alternative"]
_LANG_RE = re.compile(r"^[a-z]{2,3}(-[A-Za-z]{2})?$")


# ---- id-or-link fields -------------------------------------------------------------

class ChannelField(RefField):
    resolver = staticmethod(refs.resolve_channel)


class ChannelListField(RefField):
    resolver = staticmethod(refs.resolve_channels)

    def _deserialize(self, value, attr, data, **kwargs):
        slugs = super()._deserialize(value, attr, data, **kwargs)
        if slugs and len(slugs) > 25:
            raise ValidationError("At most 25 channels.")
        return slugs


class CategoryField(RefField):
    resolver = staticmethod(refs.resolve_category)


class ClipField(RefField):
    resolver = staticmethod(refs.resolve_clip)


class VideoField(RefField):
    resolver = staticmethod(refs.resolve_video)


class CursorField(StrippedString):
    """Opaque next_cursor from the previous page (absent = first page)."""

    def __init__(self, **kwargs):
        kwargs.setdefault("required", False)
        kwargs.setdefault("load_default", None)
        super().__init__(**kwargs)


class LanguagesField(fields.Field):
    """'en, es,pt' -> ['en', 'es', 'pt'] (Kick language codes, max 10)."""

    def __init__(self, **kwargs):
        kwargs.setdefault("load_default", None)
        super().__init__(**kwargs)

    def _deserialize(self, value, attr, data, **kwargs):
        out = []
        for raw in str(value).split(","):
            code = raw.strip()
            if not code:
                continue
            lang, _, region = code.replace("_", "-").partition("-")
            code = lang.lower() + (f"-{region.upper()}" if region else "")
            if not _LANG_RE.match(code):
                raise ValidationError(f"'{raw.strip()}' is not a language code (en, es, pt, en-IN ...).")
            if code not in out:
                out.append(code)
        if len(out) > 10:
            raise ValidationError("At most 10 languages.")
        return out or None


class LanguageField(StrippedString):
    def __init__(self, **kwargs):
        kwargs.setdefault("required", False)
        kwargs.setdefault("load_default", "en")
        super().__init__(**kwargs)

    def _deserialize(self, value, attr, data, **kwargs):
        value = super()._deserialize(value, attr, data, **kwargs)
        if value is None:
            return "en"
        lang, _, region = value.replace("_", "-").partition("-")
        value = lang.lower() + (f"-{region.upper()}" if region else "")
        if not _LANG_RE.match(value):
            raise ValidationError("Must be a language code (en, es, pt, en-IN ...).")
        return value


class TimestampField(StrippedString):
    """ISO date or datetime ('2026-09-21', '2026-09-21T07:00:00Z',
    '2026-09-21 07:00') -> '2026-09-21T07:00:00.000Z' (UTC)."""

    def __init__(self, **kwargs):
        kwargs.setdefault("required", False)
        kwargs.setdefault("load_default", None)
        super().__init__(**kwargs)

    def _deserialize(self, value, attr, data, **kwargs):
        value = super()._deserialize(value, attr, data, **kwargs)
        if value is None:
            return None
        raw = value.replace(" ", "T")
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(raw)
        except ValueError:
            raise ValidationError("Must be an ISO date/time (2026-09-21T07:00:00Z).")
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        if dt > datetime.now(timezone.utc):
            raise ValidationError("Must not be in the future.")
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _clip_sort(default="views"):
    return ChoiceField({"views": "view", "date": "date"}, load_default={"views": "view", "date": "date"}[default])


def _clip_period(default):
    return ChoiceField(["day", "week", "month", "all"], load_default=default)


# ---- schemas ---------------------------------------------------------------------------

class EmptySchema(BaseSchema):
    pass


class ChannelSchema(BaseSchema):
    channel = ChannelField()


class ChannelsSchema(BaseSchema):
    channels = ChannelListField()


class ChatUserSchema(ChannelSchema):
    user = ChannelField(metadata={"description": "username or kick.com profile link"})


class ChatMessagesSchema(ChannelSchema):
    cursor = CursorField()
    start_time = TimestampField()

    @validates_schema
    def _cursor_or_time(self, data, **kwargs):
        if data.get("cursor") and data.get("start_time"):
            raise ValidationError("Pass either cursor or start_time, not both.", "cursor")


class VideoSchema(BaseSchema):
    video = VideoField()


class ChannelClipsSchema(ChannelSchema):
    sort = _clip_sort()
    period = _clip_period("all")
    cursor = CursorField()


class CategoryClipsSchema(BaseSchema):
    category = CategoryField()
    sort = _clip_sort()
    period = _clip_period("week")
    cursor = CursorField()


class TopClipsSchema(BaseSchema):
    sort = _clip_sort()
    period = _clip_period("day")
    cursor = CursorField()


class ClipSchema(BaseSchema):
    clip = ClipField()


class LivestreamsSchema(BaseSchema):
    sort = ChoiceField(["viewers_desc", "viewers_asc", "featured"], load_default="viewers_desc")
    languages = LanguagesField()
    category = CategoryField(required=False, load_default=None)
    directory = ChoiceField(DIRECTORIES)
    tag = StrippedString(required=False, load_default=None)
    limit = LimitField(default=24, max_size=100)
    cursor = CursorField()


class FeaturedSchema(BaseSchema):
    language = LanguageField()


class CategoriesSchema(BaseSchema):
    directory = ChoiceField(DIRECTORIES)
    page = PageField(max_page=1000)
    limit = LimitField(default=24, max_size=100)


class CategorySchema(BaseSchema):
    category = CategoryField()


class SearchSchema(BaseSchema):
    query = QueryField(max_length=100)


class SearchChannelsSchema(BaseSchema):
    query = QueryField(max_length=100)
    is_live = Flag()
    sort = ChoiceField(["relevance", "followers"], load_default="relevance")
    page = PageField(max_page=100)
    limit = LimitField(default=20, max_size=100)


class SearchCategoriesSchema(BaseSchema):
    query = QueryField(max_length=100)
    is_live = Flag()
    page = PageField(max_page=100)
    limit = LimitField(default=20, max_size=100)

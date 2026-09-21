"""/kick/chat/* — chat history of a channel (works whether or not the
channel is live; Kick keeps the recent backlog)."""
from kick import parsers as P
from kick import shared
from kick.fetch import legacy


def messages(channel, cursor=None, start_time=None):
    """Up to 25 chat messages, newest first. `cursor` (the previous page's
    next_cursor) walks back in time; `start_time` jumps to the messages
    around an ISO timestamp (e.g. a VOD moment)."""
    cid = shared.channel_id(channel)
    params = {"cursor": cursor, "start_time": start_time}
    body = legacy(f"/api/v2/channels/{cid}/messages", params)
    data = body.get("data") if isinstance(body, dict) else None
    return {"channel": channel, **P.chat_history(data)}

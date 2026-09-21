"""Cache TTL per /kick/* endpoint (cache.py, keyed on the validated params).

Tiers follow how fast Kick moves each surface: a livestream's viewer count
changes every few seconds, a finished VOD or clip never changes again, and
the category catalogue changes a few times a day.
"""
from datetime import timedelta

# --- live surfaces -----------------------------------------------------------
# Live status / viewers / uptime: the site itself repolls every ~30-60 s.
LIVE_CACHE = timedelta(seconds=30)
# The browse directory and featured shelf.
BROWSE_CACHE = timedelta(seconds=45)
# Chat history and active chatters.
CHAT_CACHE = timedelta(seconds=20)
# Polls and predictions run for minutes.
POLL_CACHE = timedelta(seconds=20)

# --- channel -----------------------------------------------------------------
# Profile, socials, badges, emotes, chatroom settings: edited rarely.
CHANNEL_CACHE = timedelta(minutes=5)
LINKS_CACHE = timedelta(hours=1)
EMOTES_CACHE = timedelta(hours=1)
# Gift leaderboards move with every gifted sub.
LEADERBOARD_CACHE = timedelta(minutes=2)
GOALS_CACHE = timedelta(minutes=2)

# --- videos / clips ----------------------------------------------------------
# A channel's VOD list gains one row per stream.
VIDEOS_CACHE = timedelta(minutes=5)
VIDEO_CACHE = timedelta(minutes=30)
# Clip lists reorder as views land; a clip itself is immutable bar its count.
CLIPS_CACHE = timedelta(minutes=5)
CLIP_CACHE = timedelta(minutes=30)

# --- catalogues / search -----------------------------------------------------
# Directories (Games / IRL / ...) never change.
DIRECTORIES_CACHE = timedelta(days=1)
# The category list carries live viewer counts (sorted by them).
CATEGORIES_CACHE = timedelta(minutes=2)
CATEGORY_CACHE = timedelta(minutes=5)
LANGUAGES_CACHE = timedelta(days=1)
SEARCH_CACHE = timedelta(minutes=5)

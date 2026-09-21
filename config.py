"""Configuration for the Kick Scraper. Everything can be set with an
environment variable; the defaults work out of the box.

    PORT        port the API listens on (default 8000)
    KICK_PROXY  proxy URL for every request, e.g. http://user:pass@host:port
                (default: none — direct). Kick's public JSON APIs answered a
                40-request burst from one IP without a single block, so you
                very likely don't need this. Set it only if you start seeing
                403 / 429 at high volume.

Everything else below is a plain constant with a working default — edit it
here if you need to.
"""
import os

PORT = int(os.environ.get("PORT", "8000"))

# Retry policy for transport errors and blocks (every request).
MAX_RETRIES = 3
RETRY_BACKOFF = 2          # seconds, multiplied by the attempt number

# Kick's public search-only Typesense key, shipped in kick.com's own JS
# bundle. If Kick rotates it, the scraper re-reads the new one from the
# bundle by itself.
KICK_TYPESENSE_API_KEY = "nXIMW0iEN6sMujFYjFuhdrSwVow3pDQu"

# Block fallback: after a 403 / 429 new sessions may switch to a separate
# proxy for KICK_BLOCK_COOLDOWN seconds. Off here — with KICK_PROXY set every
# request already goes through it.
KICK_FALLBACK_PROXY_COUNTRY = None
KICK_BLOCK_COOLDOWN = 900


def kick_proxy():
    """Proxy URL for a new session (None = direct)."""
    return os.environ.get("KICK_PROXY") or None


def kick_fallback_proxy():
    """Proxy for a blocked worker (None = no fallback; see above)."""
    return None

"""Use the scraper straight from Python — no server needed.

    python main.py

Every function returns the same JSON the API does; results are written to
output/*.json. The functions live in kick/ (channels, chat, videos, clips,
browse, categories, search). Channel, category, clip and video inputs take
the same validated refs the API builds, so go through kick.refs first.
"""
import json
import os

from kick import browse, channels, refs

os.makedirs("output", exist_ok=True)


def save(name, data):
    path = os.path.join("output", name)
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"saved {path}")


if __name__ == "__main__":
    # a channel slug or any kick.com channel link
    save("channel_xqc.json", channels.details(refs.resolve_channel("https://kick.com/xqc")))

    # is it live right now? viewers, uptime, title, category
    save("status_adinross.json", channels.status(refs.resolve_channel("adinross")))

    # the most watched live streams on Kick right now
    save("livestreams_top.json", browse.livestreams(limit=24))

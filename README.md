# 🟢 Kick Scraper

Kick Scraper is a **free and open-source** scraper that gets you **unlimited** detailed Kick data for free.

## ✨ What Can I Get?

- 📺 **Full profiles on 120M+ Kick channels** — followers, sub price, socials, badges, links & live stream
- 🔴 **Every live stream, right now** — viewers, uptime, title, category & HLS link; filter by language, category or tag
- 💬 **Chat & community** — chat history, who's in chat, gift leaderboards, predictions, polls & goals
- 🎞️ **VODs, clips & 12,900+ categories** — views, likes, playback links and top clips by day, week or month

## 🎥 Example: A Full Kick Channel

```json
{
  "channel": {
    "id": 668,
    "slug": "xqc",
    "username": "xQc",
    "link": "https://kick.com/xqc",
    "bio": "THE BEST AT ABSOLUTELY EVERYTHING. THE JUICER. LEADER OF THE JUICERS.",
    "is_live": false,
    "is_verified": true,
    "followers_count": 1113893,
    "subscription": { "price": 4.99, "currency": "USD" },
    "socials": {
      "instagram": "https://instagram.com/xqcow1",
      "twitter": "https://x.com/xqc",
      "youtube": "https://youtube.com/channel/UCmDTrq0LNgPodDOFZiSbsww",
      "discord": "https://discord.gg/xqcow"
    },
    "links": [
      { "id": 605185, "link": "https://streamelements.com/xqc/tip", "order": 1 }
    ],
    "recent_categories": [
      { "id": 15, "name": "Just Chatting", "slug": "just-chatting", "viewer_count": 67330 },
      { "id": 8, "name": "Grand Theft Auto V (GTA)", "slug": "grand-theft-auto-v", "viewer_count": 62163 }
    ],
    "subscriber_badges": [
      { "id": 97968, "months": 1, "image": "https://files.kick.com/channel_subscriber_badges/97968/conversion/original-fullsize.png" }
    ],
    "created_at": "2022-10-22T06:59:51Z"
  }
}
```

*Trimmed for readability.*

## 🚀 Unlimited Free Kick Data — Get It in 60 Seconds

1️⃣ Clone and install:
```bash
git clone https://github.com/omkarcloud/kick-scraper
cd kick-scraper
python -m pip install -r requirements.txt
```

2️⃣ Start the API:
```bash
python run.py
```

3️⃣ Get your first data:
```bash
curl "http://localhost:8000/channels/details?channel=xqc"
```

```json
{
  "channel": {
    "id": 668,
    "slug": "xqc",
    "username": "xQc",
    "link": "https://kick.com/xqc",
    "is_live": false,
    "is_verified": true,
    "followers_count": 1113893,
    "subscription": { "price": 4.99, "currency": "USD" },
    "socials": {
      "instagram": "https://instagram.com/xqcow1",
      "twitter": "https://x.com/xqc",
      "youtube": "https://youtube.com/channel/UCmDTrq0LNgPodDOFZiSbsww",
      "discord": "https://discord.gg/xqcow",
      "tiktok": null,
      "facebook": null
    },
    "created_at": "2022-10-22T06:59:51Z"
  }
}
```

All 31 endpoints are now live at `http://localhost:8000`.

## 📚 Endpoints

31 endpoints cover everything you need.

| Endpoint | Path | Returns |
|---|---|---|
| Channel Details | `/channels/details` | Full channel card: followers, sub price, socials, badges and live stream |
| Channel Live Status / Batch | `/channels/status`, `/channels/status/batch` | Live right now? Viewers and uptime, for 1 or 25 channels |
| Search | `/search` | Top channels, categories and live streams for any query |
| Search Channels / Categories | `/search/channels`, `/search/categories` | Every match, filter to live, sort by followers |
| Live Streams | `/livestreams` | Every live stream, filtered by language, category or tag |
| Featured Streams / Stream Languages | `/livestreams/featured`, `/livestreams/languages` | Homepage featured streams and every supported language |
| Chat Messages | `/chat/messages` | Chat history with badges, emotes and replies, 25 per page |
| Chatters / Chat User | `/channels/chatters`, `/channels/chat-user` | Who's in chat, and any user's badges, subs and bans |
| Chat Settings | `/channels/chatroom` | Slow, followers-only and subs-only modes, rules, pinned message |
| Gift Leaderboards | `/channels/leaderboards` | Top sub and Kicks gifters: all-time, month, week |
| Latest Prediction / Current Poll | `/channels/prediction`, `/channels/poll` | Outcomes, points, return rates and live poll votes |
| Channel Goals / Point Rewards | `/channels/goals`, `/channels/rewards` | Follower and sub goals, and every channel-points reward |
| Channel Emotes / Links / Recent Categories | `/channels/emotes`, `/channels/links`, `/channels/recent-categories` | Emotes with images, About-page links, recent categories |
| Playback Link | `/channels/playback` | The live HLS playlist, ready for any player |
| Channel Videos / Video Details | `/videos`, `/videos/details` | Past broadcasts with views, duration and HLS links |
| Channel / Top / Category Clips | `/clips`, `/clips/top`, `/clips/category` | Clips by views or date, today to all time |
| Clip Details | `/clips/details` | One clip with views, likes, creator and playback link |
| Categories / Category Details / Directories | `/categories`, `/categories/details`, `/categories/directories` | 12,900+ categories ranked by live viewers |


## 🔍 Exploring Parameters

The same API is published on RapidAPI, and its playground is the easiest place to try parameters and see raw responses. Once a request looks right, run it locally for **unlimited free** data.

1. [Subscribe to the free plan](https://rapidapi.com/OmkarCloud/api/best-kick-scraper-free-1000-calls/pricing) — 1,000 calls/month, no credit card.
2. [Try the endpoints in the playground](https://rapidapi.com/OmkarCloud/api/best-kick-scraper-free-1000-calls/playground) — every param is pre-filled, so you see real data in one click.
3. Copy the generated code and replace `https://best-kick-scraper-free-1000-calls.p.rapidapi.com` with `http://localhost:8000`. It will now run against your local API.

```python
import requests

# generated by the playground, host swapped for the local API
response = requests.get(
    "http://localhost:8000/channels/details",
    params={"channel": "xqc"},
)
print(response.json())
```

## 💬 Have Questions? We Have Answers.

You're a developer — we know how hard completing a project can be. So we offer full support: just message us and we'll reply ✅ with a solution within 1 working day.

[![Message Us on WhatsApp about Kick Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/whatsapp-us.png)](https://api.whatsapp.com/send?phone=918178804274&text=I%20need%20help%20using%20the%20Kick%20Scraper%20API.)

[![Ask Us by Email about Kick Scraper](https://raw.githubusercontent.com/omkarcloud/assets/master/images/ask-on-email.png)](mailto:happy.to.help@omkar.cloud?subject=Help%20with%20Kick%20Scraper%20API&body=I%20need%20help%20using%20the%20Kick%20Scraper%20API.)

## ⚡ Popular Scrapers by Omkar Cloud

- [**Google Maps Scraper (3,100+ GitHub Stars)**](https://github.com/omkarcloud/google-maps-scraper) — type "dentists in New York", get every business as a ready-to-call lead list: phones, emails, websites & reviews. Up to 100K free leads/month.
- [**G2 Scraper**](https://www.omkar.cloud/tools/g2-scraper) — G2 product details, ratings & AI-found contacts
- [**Website Email Contact Scraper**](https://www.omkar.cloud/tools/website-email-contact-scraper) — emails, phones & socials from any website
- [**AliExpress Scraper**](https://www.omkar.cloud/tools/aliexpress-scraper-api) — live product details, SKU variants, stock & shipping
- [**Booking Scraper**](https://www.omkar.cloud/tools/booking-scraper) — Booking.com hotels: prices, ratings, rooms & amenities
- [**Etsy Scraper**](https://www.omkar.cloud/tools/etsy-scraper) — Etsy products: prices, discounts, shops & variations

## ⭐ Love It? [Star It ⭐!](https://github.com/omkarcloud/kick-scraper)

Star the repo ⭐ and become my star hero!

It's just 1 click, but it means the world to me.

[![Star us on GitHub](https://raw.githubusercontent.com/omkarcloud/google-maps-scraper/master/screenshots/star-us.png)](https://github.com/omkarcloud/kick-scraper)

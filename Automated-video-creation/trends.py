#!/usr/bin/env python3
"""
Trend research + performance feedback (free public sources only).

Every day (cached in state.json) it:
  1. collects signals: Google Trends daily searches (RSS), most-viewed Wikipedia articles,
     and - if YT_API_KEY is set - YouTube's trending videos and top recent Shorts in our niches
  2. asks the LLM to turn them into SAFE, evergreen explainer ideas (no celebrities, politics, tragedies...)
     plus the video formats / title patterns that seem to work
  3. looks at how our own earlier videos performed (public view counts) and re-weights categories/styles

Optional env vars: YT_API_KEY (free Google API key), TREND_GEOS ("US,IN,GB"), TREND_REGION ("US"),
TREND_SEARCHES (YouTube searches per day, 100 quota units each; default 2)
"""
import json
import os
import random
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

UA = {"User-Agent": "AutoVideoBot/1.0 (+https://github.com/TheRaptar/Automated-video-creation-)"}
YT_API_KEY = os.environ.get("YT_API_KEY", "")
YT_API = os.environ.get("YT_API_BASE", "https://www.googleapis.com/youtube/v3")
GT_URL = os.environ.get("GT_RSS_URL", "https://trends.google.com/trending/rss?geo={geo}")
WIKI_URL = os.environ.get("WIKI_TOP_URL",
                          "https://wikimedia.org/api/rest_v1/metrics/pageviews/top/en.wikipedia/all-access/{date}")
GEOS = [g.strip() for g in os.environ.get("TREND_GEOS", "US,IN,GB").split(",") if g.strip()]
YT_REGION = os.environ.get("TREND_REGION", "US")
SEARCHES = int(os.environ.get("TREND_SEARCHES", "2"))
WIKI_SKIP = ("Main_Page", "Special:", "Wikipedia:", "Portal:", "Help:", "File:", "Category:",
             "Template:", "Talk:", "User:", "-")


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


# ------------------------------------------------------------ signal collectors
def google_trends(geo: str) -> list[dict]:
    try:
        r = requests.get(GT_URL.format(geo=geo), headers=UA, timeout=30)
        if not r.ok:
            print(f"  Google Trends {geo}: HTTP {r.status_code}")
            return []
        root = ET.fromstring(r.content)
    except Exception as e:
        print(f"  Google Trends {geo} failed: {type(e).__name__}")
        return []
    out = []
    for item in root.iter("item"):
        title, traffic, news = (item.findtext("title") or "").strip(), "", []
        for el in item.iter():
            tag = el.tag.split("}")[-1]
            if tag == "approx_traffic":
                traffic = (el.text or "").strip()
            elif tag == "news_item_title" and len(news) < 2:
                news.append((el.text or "").strip())
        if title:
            out.append({"term": title, "traffic": traffic, "news": news})
    return out[:15]


def wikipedia_top() -> list[dict]:
    now = datetime.now(timezone.utc)
    for back in (1, 2, 3):                      # the newest day is often not published yet
        date = (now - timedelta(days=back)).strftime("%Y/%m/%d")
        try:
            r = requests.get(WIKI_URL.format(date=date), headers=UA, timeout=30)
            if r.ok:
                arts = r.json()["items"][0]["articles"]
                return [{"title": a["article"].replace("_", " "), "views": a["views"]}
                        for a in arts if not a["article"].startswith(WIKI_SKIP)][:40]
        except Exception as e:
            print(f"  Wikipedia top ({date}) failed: {type(e).__name__}")
    return []


def _secs(iso: str) -> int:
    m = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m:
        return 0
    h, mi, s = (int(x or 0) for x in m.groups())
    return h * 3600 + mi * 60 + s


def _yt(path: str, **params) -> dict:
    r = requests.get(f"{YT_API}/{path}", params={**params, "key": YT_API_KEY}, timeout=30)
    r.raise_for_status()
    return r.json()


def youtube_signals(categories: list[str]) -> dict:
    if not YT_API_KEY:
        return {}
    out = {"trending": [], "shorts": []}
    for cat in ("28", "27", None):              # Science & Tech, Education, everything
        params = dict(part="snippet,statistics,contentDetails", chart="mostPopular",
                      regionCode=YT_REGION, maxResults=15)
        if cat:
            params["videoCategoryId"] = cat
        try:
            for it in _yt("videos", **params).get("items", []):
                out["trending"].append({"title": it["snippet"]["title"],
                                        "views": int(it["statistics"].get("viewCount", 0)),
                                        "secs": _secs(it["contentDetails"].get("duration"))})
        except Exception as e:
            print(f"  YouTube trending (category {cat}) failed: {type(e).__name__}")
    since = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    for q in random.sample(categories, min(SEARCHES, len(categories))):
        try:
            res = _yt("search", part="snippet", type="video", videoDuration="short", order="viewCount",
                      publishedAfter=since, q=q, maxResults=8, regionCode=YT_REGION)
            ids = [i["id"]["videoId"] for i in res.get("items", []) if i.get("id", {}).get("videoId")]
            stats = {v["id"]: int(v["statistics"].get("viewCount", 0))
                     for v in _yt("videos", part="statistics", id=",".join(ids)).get("items", [])} if ids else {}
            for i in res.get("items", []):
                vid = i.get("id", {}).get("videoId")
                out["shorts"].append({"niche": q, "title": i["snippet"]["title"], "views": stats.get(vid, 0)})
        except Exception as e:
            print(f"  YouTube Shorts search '{q}' failed: {type(e).__name__}")
    return out


# ------------------------------------------------------------ analysis
def _signals_text(sig: dict) -> str:
    parts = []
    for geo, items in sig.get("google", {}).items():
        parts.append(f"Google Trends daily searches ({geo}): " + "; ".join(
            f"{i['term']} ({i['traffic']})" + (f" - news: {i['news'][0]}" if i["news"] else "") for i in items))
    if sig.get("wiki"):
        parts.append("Most-viewed Wikipedia articles yesterday: " + "; ".join(
            f"{w['title']} ({w['views']:,})" for w in sig["wiki"]))
    yt = sig.get("youtube", {})
    if yt.get("trending"):
        parts.append("YouTube trending videos: " + "; ".join(
            f"{v['title']} ({v['views']:,} views, {v['secs']}s)" for v in yt["trending"][:30]))
    if yt.get("shorts"):
        parts.append("Top Shorts of the last 7 days in our niches: " + "; ".join(
            f"[{s['niche']}] {s['title']} ({s['views']:,} views)" for s in yt["shorts"]))
    return "\n".join(parts)


def analyze(sig: dict, llm_json, categories: list[str]) -> dict | None:
    history = []
    try:
        history = json.loads(Path("history.json").read_text(encoding="utf-8"))[-60:]
    except Exception:
        pass
    prompt = f"""You are the lead Trend Analyst and Creative Strategist for a high-retention Adult Glamour, Seduction Psychology, and Romantic Allure YouTube Shorts and Instagram Reels channel.
Niches: {', '.join(categories)}. Today is {_today()}.

SIGNALS (what people search for and watch right now):
{_signals_text(sig)}

Turn trending cultural conversations, relationship queries, and psychological hooks into bold, seductive, high-engagement video concepts. Return ONLY JSON:
{{"ideas": [{{"topic": "specific attraction or romantic glamour topic", "angle": "the psychological secret, visual allure, or tension trigger",
  "why_trending": "which signal(s) inspired it", "format": "short|long|story",
  "style": "allure|chemistry|mystery|charm|seduction|romance", "score": 1-10}}],
 "format_trends": ["video formats, hooks, or visual styles that visibly generate viral retention"],
 "title_patterns": ["high-CTR curiosity title patterns seen in top romantic/lifestyle shorts"]}}

Rules:
- 12 ideas: 6 "short" (fast-paced viral Shorts), 3 "long" (deep-dive masterclass), 3 "story" (cinematic sensual narrative featuring adult fictional characters 25+).
- Convert trends into high-retention concepts exploring romantic psychology, subconscious chemistry triggers, non-verbal seduction, bedroom/luxury hotel aesthetics, and magnetic confidence.
- Visual style focus: Fictional adult characters aged 25+, glamorous lingerie-inspired fashion with full coverage, intimate warm lighting, luxury hotel suites, romantic bedrooms, and cinematic close-ups.
- NEVER include: real living people by name, celebrity gossip, politics, tragedy, explicit pornography, visible nudity, non-consensual content, or medical advice.
- Do not repeat or closely resemble these earlier topics: {'; '.join(history) or 'none'}.
- score = expected viral retention x romantic intrigue x aesthetic fit for the glamour niche."""
    valid = lambda d: (isinstance(d, dict) and isinstance(d.get("ideas"), list)
                       and sum(isinstance(i, dict) and isinstance(i.get("topic"), str) for i in d["ideas"]) >= 3)
    return llm_json(prompt, rounds=2, valid=valid)


def ensure_fresh(state: dict, llm_json, categories: list[str]) -> None:
    """Refresh the daily trend ideas (once per UTC day) and the performance weights."""
    today = _today()
    if (state.get("trends") or {}).get("date") == today:
        return
    print("  Researching today's trends...")
    update_performance(state)
    sig = {"google": {g: google_trends(g) for g in GEOS}, "wiki": wikipedia_top(),
           "youtube": youtube_signals(categories)}
    if not (any(sig["google"].values()) or sig["wiki"] or sig["youtube"]):
        print("  No trend signals reachable - using normal topic selection.")
        return
    data = analyze(sig, llm_json, categories)
    if not data:
        print("  Trend analysis failed - using normal topic selection.")
        return
    ideas = []
    for i in data["ideas"]:
        if not (isinstance(i, dict) and isinstance(i.get("topic"), str)):
            continue
        try:
            score = float(i.get("score", 5))
        except (TypeError, ValueError):
            score = 5.0
        ideas.append({"topic": i["topic"].strip(), "angle": str(i.get("angle", "")).strip(),
                      "why_trending": str(i.get("why_trending", "")).strip(),
                      "format": i.get("format") if i.get("format") in ("short", "long", "story") else "short",
                      "style": i.get("style"), "score": score, "used": False})
    state["trends"] = {"date": today, "ideas": ideas,
                       "format_trends": [str(x) for x in data.get("format_trends", [])][:5],
                       "title_patterns": [str(x) for x in data.get("title_patterns", [])][:5]}
    print(f"  {len(ideas)} trend-based ideas ready. Format trends: {state['trends']['format_trends']}")


def pick_idea(fmt: str, state: dict):
    cands = [i for i in (state.get("trends") or {}).get("ideas", [])
             if not i.get("used") and i.get("format") == fmt]
    if not cands:
        return None
    cands.sort(key=lambda i: -i.get("score", 5))
    pick = random.choice(cands[:3])
    pick["used"] = True
    return dict(pick)


# ------------------------------------------------------------ performance feedback loop
def update_performance(state: dict) -> None:
    """Public view counts of our own videos -> relative weights per category and style."""
    vids = state.get("videos", [])[-100:]
    if not (YT_API_KEY and vids):
        return
    views = {}
    try:
        for i in range(0, len(vids), 50):
            ids = ",".join(v["id"] for v in vids[i:i + 50])
            for it in _yt("videos", part="statistics", id=ids).get("items", []):
                views[it["id"]] = int(it["statistics"].get("viewCount", 0))
    except Exception as e:
        print(f"  Performance check failed: {type(e).__name__}")
        return
    now, rows = datetime.now(timezone.utc), []
    for v in vids:
        if v["id"] not in views:
            continue
        v["views"] = views[v["id"]]
        try:
            age = (now - datetime.fromisoformat(v["ts"])).total_seconds() / 86400
        except Exception:
            continue
        if age >= 2:                                    # let a video settle for 2 days first
            rows.append((v, v["views"] / age))
    if len(rows) < 4:
        return
    overall = sum(s for _, s in rows) / len(rows) or 1.0
    weights = {}
    for key in ("category", "style", "source"):
        groups = {}
        for v, s in rows:
            if v.get(key):
                groups.setdefault(v[key], []).append(s)
        weights[key] = {k: round(min(2.0, max(0.5, (sum(x) / len(x)) / overall)), 2)
                        for k, x in groups.items() if len(x) >= 2}
    state["weights"] = weights
    print(f"  Performance weights updated: {weights}")

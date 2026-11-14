#!/usr/bin/env python3
"""
Intelligent Topic Research, Growth Scoring & Channel Learning Engine
====================================================================
Collects real audience demand signals from free public sources:
  1. Google Trends daily trending searches (RSS)
  2. Google News RSS headlines (timely rising interest)
  3. Wikipedia top pageviews (curiosity & encyclopedic demand)
  4. Reddit hot discussions (community pain points, viral stories, debates)
  5. YouTube Search Autocomplete suggestions (actual viewer search demand)
  6. YouTube Data API trending & recent Shorts (when YT_API_KEY is set)

Evaluates every candidate topic across 7 growth dimensions (popularity, search demand,
competition, audience interest, trending potential, originality, engagement potential),
prevents near-duplicate topics, and updates strategic weights from YouTube Analytics.
"""
import json
import os
import random
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

import requests

UA = {"User-Agent": "RAPTAR-GrowthEngine/2.0 (+https://github.com/TheRaptar/Automated-video-creation-)"}
YT_API_KEY = os.environ.get("YT_API_KEY", "")
YT_API = os.environ.get("YT_API_BASE", "https://www.googleapis.com/youtube/v3")
GT_URL = os.environ.get("GT_RSS_URL", "https://trends.google.com/trending/rss?geo={geo}")
GNEWS_URL = os.environ.get("GNEWS_RSS_URL", "https://news.google.com/rss/search?q={q}&hl=en-US&gl=US&ceid=US:en")
WIKI_URL = os.environ.get(
    "WIKI_TOP_URL",
    "https://wikimedia.org/api/rest_v1/metrics/pageviews/top/en.wikipedia/all-access/{date}",
)
YT_SUGGEST_URL = "https://suggestqueries.google.com/complete/search"
GEOS = [g.strip() for g in os.environ.get("TREND_GEOS", "US,IN,GB").split(",") if g.strip()]
YT_REGION = os.environ.get("TREND_REGION", "US")
SEARCHES = int(os.environ.get("TREND_SEARCHES", "3"))
REDDIT_SUBS = [
    s.strip()
    for s in os.environ.get(
        "REDDIT_SUBS",
        "todayilearned,ExplainLikeImFive,mythology,nosleep,animation,Futurology",
    ).split(",")
    if s.strip()
]
WIKI_SKIP = (
    "Main_Page", "Special:", "Wikipedia:", "Portal:", "Help:", "File:",
    "Category:", "Template:", "Talk:", "User:", "-",
)


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _norm_tokens(text: str) -> set[str]:
    stop = {"the", "and", "for", "with", "that", "this", "from", "into", "about", "what", "how", "why", "who"}
    words = re.findall(r"[a-z0-9\u0080-\uffff]{3,}", (text or "").lower())
    return {w for w in words if w not in stop}


def is_duplicate_topic(topic: str, history: list[str], recent_videos: list[dict] = None, threshold: float = 0.48) -> bool:
    """Detects near-duplicate or already-published topics via normalized token similarity."""
    cand = _norm_tokens(topic)
    if not cand:
        return False
    prior_texts = list(history or []) + [str(v.get("title") or v.get("topic") or "") for v in (recent_videos or [])]
    for prev in prior_texts[-150:]:
        ptoks = _norm_tokens(prev)
        if not ptoks:
            continue
        inter = len(cand & ptoks)
        union = len(cand | ptoks)
        min_len = max(1, min(len(cand), len(ptoks)))
        if (union > 0 and (inter / union) >= threshold) or (inter / min_len) >= 0.65:
            return True
    return False


# ------------------------------------------------------------ signal collectors
def google_trends(geo: str) -> list[dict]:
    try:
        r = requests.get(GT_URL.format(geo=geo), headers=UA, timeout=20)
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


def google_news(queries: list[str]) -> list[dict]:
    """Fetches rising headlines via public Google News RSS for selected topic pillars."""
    out = []
    for q in queries[:3]:
        try:
            r = requests.get(GNEWS_URL.format(q=quote(q[:60])), headers=UA, timeout=15)
            if not r.ok:
                continue
            root = ET.fromstring(r.content)
            for item in list(root.iter("item"))[:5]:
                title = (item.findtext("title") or "").strip()
                if title:
                    out.append({"query": q, "headline": title.split(" - ")[0].strip()})
        except Exception:
            continue
    return out[:15]


def wikipedia_top() -> list[dict]:
    now = datetime.now(timezone.utc)
    for back in (1, 2, 3):
        date = (now - timedelta(days=back)).strftime("%Y/%m/%d")
        try:
            r = requests.get(WIKI_URL.format(date=date), headers=UA, timeout=20)
            if r.ok:
                arts = r.json()["items"][0]["articles"]
                return [
                    {"title": a["article"].replace("_", " "), "views": a["views"]}
                    for a in arts
                    if not a["article"].startswith(WIKI_SKIP)
                ][:35]
        except Exception as e:
            print(f"  Wikipedia top ({date}) failed: {type(e).__name__}")
    return []


def reddit_hot(subs: list[str] = None) -> list[dict]:
    """Collects high-upvote public Reddit posts showing genuine audience curiosity & discussion."""
    out = []
    for sub in (subs or REDDIT_SUBS)[:5]:
        try:
            r = requests.get(
                f"https://www.reddit.com/r/{sub}/hot.json",
                params={"limit": 6},
                headers={"User-Agent": "python:raptar.growth.research:2.0 (by /u/raptar_bot)"},
                timeout=12,
            )
            if not r.ok:
                continue
            for child in r.json().get("data", {}).get("children", []):
                d = child.get("data", {})
                if d.get("stickied") or d.get("over_18"):
                    continue
                title = (d.get("title") or "").strip()
                if title:
                    out.append({
                        "sub": sub,
                        "title": title[:160],
                        "score": int(d.get("score") or 0),
                        "comments": int(d.get("num_comments") or 0),
                    })
        except Exception:
            continue
    out.sort(key=lambda x: -(x["score"] + x["comments"] * 3))
    return out[:20]


def youtube_autocomplete(seed_queries: list[str]) -> list[str]:
    """Queries public YouTube Search Suggest API to discover real viewer search phrases."""
    suggestions: list[str] = []
    for q in seed_queries[:4]:
        clean = re.sub(r"[^a-zA-Z0-9\s]", " ", q).strip()[:40]
        if not clean:
            continue
        try:
            r = requests.get(
                YT_SUGGEST_URL,
                params={"client": "firefox", "ds": "yt", "q": clean},
                headers=UA,
                timeout=10,
            )
            if r.ok:
                data = r.json()
                if isinstance(data, list) and len(data) > 1 and isinstance(data[1], list):
                    for s in data[1][:6]:
                        if isinstance(s, str) and s not in suggestions:
                            suggestions.append(s)
        except Exception:
            continue
    return suggestions[:20]


def _secs(iso: str) -> int:
    m = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m:
        return 0
    h, mi, s = (int(x or 0) for x in m.groups())
    return h * 3600 + mi * 60 + s


def _yt(path: str, **params) -> dict:
    r = requests.get(f"{YT_API}/{path}", params={**params, "key": YT_API_KEY}, timeout=20)
    r.raise_for_status()
    return r.json()


def youtube_signals(categories: list[str]) -> dict:
    if not YT_API_KEY:
        return {}
    out = {"trending": [], "shorts": [], "competition": {}}
    for cat in ("28", "27", "24"):
        params = dict(
            part="snippet,statistics,contentDetails",
            chart="mostPopular",
            regionCode=YT_REGION,
            maxResults=12,
            videoCategoryId=cat,
        )
        try:
            for it in _yt("videos", **params).get("items", []):
                out["trending"].append({
                    "title": it["snippet"]["title"],
                    "views": int(it["statistics"].get("viewCount", 0)),
                    "secs": _secs(it["contentDetails"].get("duration")),
                })
        except Exception as e:
            print(f"  YouTube trending (category {cat}) failed: {type(e).__name__}")
    since = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    for q in random.sample(categories, min(SEARCHES, len(categories))):
        try:
            res = _yt(
                "search",
                part="snippet",
                type="video",
                videoDuration="short",
                order="viewCount",
                publishedAfter=since,
                q=q,
                maxResults=8,
                regionCode=YT_REGION,
            )
            ids = [i["id"]["videoId"] for i in res.get("items", []) if i.get("id", {}).get("videoId")]
            stats = (
                {
                    v["id"]: int(v["statistics"].get("viewCount", 0))
                    for v in _yt("videos", part="statistics", id=",".join(ids)).get("items", [])
                }
                if ids
                else {}
            )
            view_vals = list(stats.values()) or [0]
            out["competition"][q] = {
                "result_count": int(res.get("pageInfo", {}).get("totalResults", len(ids))),
                "avg_top_views": int(sum(view_vals) / max(1, len(view_vals))),
            }
            for i in res.get("items", []):
                vid = i.get("id", {}).get("videoId")
                out["shorts"].append({
                    "niche": q,
                    "title": i["snippet"]["title"],
                    "views": stats.get(vid, 0),
                })
        except Exception as e:
            print(f"  YouTube Shorts search '{q}' failed: {type(e).__name__}")
    return out


# ------------------------------------------------------------ multi-factor growth scoring
def score_topic_idea(idea: dict, sig: dict, history: list[str], learnings: dict = None) -> tuple[float, dict]:
    """
    Scores a topic candidate (0-10) across 7 growth dimensions:
      popularity, search_demand, competition (inverse saturation),
      audience_interest, trending_potential, originality, engagement_potential.
    """
    topic = str(idea.get("topic", ""))
    angle = str(idea.get("angle", ""))
    combined_toks = _norm_tokens(f"{topic} {angle} {idea.get('why_trending', '')}")

    # 1. Popularity: match vs Google Trends / Wikipedia / YouTube trending
    gt_toks = set()
    for items in (sig.get("google") or {}).values():
        for it in items:
            gt_toks |= _norm_tokens(it.get("term", ""))
    wiki_toks = set()
    for w in sig.get("wiki") or []:
        wiki_toks |= _norm_tokens(w.get("title", ""))
    pop_hits = len(combined_toks & (gt_toks | wiki_toks))
    popularity = min(10.0, 5.2 + pop_hits * 1.4)

    # 2. Search demand: match vs YouTube autocomplete phrases & LLM searchability rating
    suggest_toks = set()
    for s in sig.get("yt_suggest") or []:
        suggest_toks |= _norm_tokens(s)
    sug_hits = len(combined_toks & suggest_toks)
    llm_demand = float(idea.get("search_demand", 6.5) or 6.5)
    search_demand = min(10.0, max(3.5, llm_demand * 0.65 + min(3.5, 1.5 + sug_hits * 1.1)))

    # 3. Competition (lower saturation = higher opportunity score)
    comp_score = float(idea.get("competition_opportunity", 7.0) or 7.0)
    yt_comp = (sig.get("youtube") or {}).get("competition") or {}
    if yt_comp and idea.get("category") in yt_comp:
        avg_v = yt_comp[idea["category"]].get("avg_top_views", 0)
        if avg_v > 50_000:
            comp_score = min(10.0, comp_score + 1.0)
    competition = max(2.0, min(10.0, comp_score))

    # 4. Audience interest (Reddit upvote/comment signal + proven channel style performance)
    red_toks = set()
    for p in sig.get("reddit") or []:
        red_toks |= _norm_tokens(p.get("title", ""))
    red_hits = len(combined_toks & red_toks)
    audience_interest = min(10.0, 5.5 + red_hits * 1.3)
    if learnings and idea.get("style") in (learnings.get("winning_styles") or []):
        audience_interest = min(10.0, audience_interest + 1.4)

    # 5. Trending potential (news / Google Trends momentum)
    news_toks = set()
    for n in sig.get("news") or []:
        news_toks |= _norm_tokens(n.get("headline", ""))
    trend_hits = len(combined_toks & (gt_toks | news_toks))
    trending_potential = min(10.0, 5.4 + trend_hits * 1.4)

    # 6. Originality (penalize overlap with past history.json topics)
    max_overlap = 0.0
    for prev in (history or [])[-150:]:
        pt = _norm_tokens(prev)
        if combined_toks and pt:
            ov = len(combined_toks & pt) / max(1, len(combined_toks | pt))
            max_overlap = max(max_overlap, ov)
    originality = max(1.0, round(10.0 * (1.0 - min(0.9, max_overlap * 1.5)), 2))

    # 7. Engagement potential (curiosity gap / emotional trigger + shareability)
    eng_llm = float(idea.get("engagement_potential", idea.get("score", 7.0)) or 7.0)
    has_hook_cue = any(w in (angle + " " + topic).lower() for w in ("secret", "why", "truth", "never", "hidden", "twist", "how", "nobody"))
    engagement_potential = min(10.0, max(3.0, eng_llm + (0.7 if has_hook_cue else 0.0)))

    breakdown = {
        "popularity": round(popularity, 2),
        "search_demand": round(search_demand, 2),
        "competition": round(competition, 2),
        "audience_interest": round(audience_interest, 2),
        "trending_potential": round(trending_potential, 2),
        "originality": round(originality, 2),
        "engagement_potential": round(engagement_potential, 2),
    }
    composite = (
        popularity * 0.14
        + search_demand * 0.18
        + competition * 0.12
        + audience_interest * 0.16
        + trending_potential * 0.12
        + originality * 0.14
        + engagement_potential * 0.14
    )
    return round(min(10.0, max(1.0, composite)), 2), breakdown


# ------------------------------------------------------------ analysis
def _signals_text(sig: dict) -> str:
    parts = []
    for geo, items in sig.get("google", {}).items():
        if items:
            parts.append(
                f"Google Trends ({geo}): "
                + "; ".join(f"{i['term']} ({i['traffic']})" + (f" - {i['news'][0]}" if i["news"] else "") for i in items[:10])
            )
    if sig.get("news"):
        parts.append("Google News rising headlines: " + "; ".join(n["headline"] for n in sig["news"][:12]))
    if sig.get("yt_suggest"):
        parts.append("YouTube Viewer Search Suggestions: " + "; ".join(sig["yt_suggest"][:15]))
    if sig.get("reddit"):
        parts.append(
            "Reddit Viral Discussions: "
            + "; ".join(f"[r/{r['sub']}] {r['title']} ({r['score']} pts)" for r in sig["reddit"][:12])
        )
    if sig.get("wiki"):
        parts.append("Most-viewed Wikipedia articles: " + "; ".join(f"{w['title']} ({w['views']:,})" for w in sig["wiki"][:18]))
    yt = sig.get("youtube", {})
    if yt.get("trending"):
        parts.append(
            "YouTube trending videos: "
            + "; ".join(f"{v['title']} ({v['views']:,} views, {v['secs']}s)" for v in yt["trending"][:20])
        )
    if yt.get("shorts"):
        parts.append("Top Shorts in niches: " + "; ".join(f"[{s['niche']}] {s['title']} ({s['views']:,} views)" for s in yt["shorts"][:15]))
    return "\n".join(parts)


def analyze(sig: dict, llm_json, categories: list[str], state: dict = None) -> dict | None:
    history = []
    try:
        history = json.loads(Path("history.json").read_text(encoding="utf-8"))[-80:]
    except Exception:
        pass
    learnings = (state or {}).get("learnings") or {}
    learn_hint = ""
    if learnings:
        learn_hint = (
            f"\nCHANNEL ANALYTICS INSIGHTS (prioritize what works on our channel!):\n"
            f"- Winning styles: {learnings.get('winning_styles', [])}\n"
            f"- Top topics/themes: {learnings.get('top_topics', [])}\n"
            f"- Best title formulas: {learnings.get('top_title_patterns', [])}\n"
            f"- Best durations: Shorts={learnings.get('optimal_short_duration', 38)}s, Long={learnings.get('optimal_long_duration', 330)}s\n"
        )

    prompt = f"""You are a Chief YouTube Growth Strategist and Viral Content Researcher.
Channel Categories: {', '.join(categories)}. Today is {_today()}.
{learn_hint}
REAL PUBLIC SIGNALS (what viewers are searching, discussing, and watching right now):
{_signals_text(sig)}

Select high-opportunity video concepts designed strictly for ORGANIC YOUTUBE GROWTH (high CTR + strong 30-second retention + clear search/browse demand).
Never suggest stale topics or spammy fluff. Mix engaging storytelling, visual animated reels, and high-retention explainers/epics.

Return ONLY JSON:
{{"ideas": [{{
  "topic": "specific clear video topic",
  "category": "one of the Channel Categories",
  "angle": "exact curiosity gap or shocking narrative hook in first 3 seconds",
  "why_trending": "specific signal from Google Trends, Reddit, YouTube Suggest, News, or Wikipedia",
  "format": "short|long|story|animated",
  "style": "animated_myth|animated_comedy|animated_anime|horror|fable|thriller|scifi|legend|mystery|fact|story",
  "target_audience": "children|adults|horror|all_ages",
  "search_demand": 1-10,
  "competition_opportunity": 1-10,
  "engagement_potential": 1-10,
  "score": 1-10
}}],
 "format_trends": ["specific retention hooks, pacing techniques, or visual styles winning today"],
 "title_patterns": ["proven non-clickbait curiosity title structures"]}}

Rules:
- 12 diverse ideas across formats: 4 "animated", 4 "short", 2 "story", 2 "long" (deep multi-chapter epics).
- Every idea MUST spark instant curiosity (an unanswered question, counterintuitive fact, or vivid emotional stake).
- NEVER include living politicians, celebrity gossip, tragedy exploitation, graphic gore, or explicit content.
- Do NOT repeat or resemble any previously covered topics: {'; '.join(history) or 'none'}."""
    valid = lambda d: (
        isinstance(d, dict)
        and isinstance(d.get("ideas"), list)
        and sum(isinstance(i, dict) and isinstance(i.get("topic"), str) for i in d["ideas"]) >= 3
    )
    return llm_json(prompt, rounds=2, valid=valid)


def ensure_fresh(state: dict, llm_json, categories: list[str]) -> None:
    """Refresh daily multi-source topic research & re-rank candidates by 7-factor growth score."""
    today = _today()
    if (state.get("trends") or {}).get("date") == today:
        return
    print("  Researching real-time growth signals (Google Trends, News, Reddit, YT Suggest, Wikipedia)...")
    update_performance(state)

    seed_queries = ["amazing mystery story", "ramayana animated story", "science unexplained", "horror true story"]
    for c in (categories or [])[:3]:
        seed_queries.append(" ".join(c.split()[:3]))

    sig = {
        "google": {g: google_trends(g) for g in GEOS},
        "news": google_news(seed_queries[:3]),
        "wiki": wikipedia_top(),
        "reddit": reddit_hot(),
        "yt_suggest": youtube_autocomplete(seed_queries),
        "youtube": youtube_signals(categories),
    }
    has_sig = (
        any(sig["google"].values())
        or sig["news"]
        or sig["wiki"]
        or sig["reddit"]
        or sig["yt_suggest"]
        or sig["youtube"]
    )
    if not has_sig:
        print("  No trend signals reachable - using curated category selection.")
        return

    data = analyze(sig, llm_json, categories, state=state)
    if not data:
        print("  Trend analysis skipped (LLM unavailable) - keeping fallback topics.")
        return

    history = []
    try:
        history = json.loads(Path("history.json").read_text(encoding="utf-8"))
    except Exception:
        pass
    recent_videos = state.get("videos", [])

    ideas = []
    for i in data["ideas"]:
        if not (isinstance(i, dict) and isinstance(i.get("topic"), str)):
            continue
        topic_str = i["topic"].strip()
        if is_duplicate_topic(topic_str, history, recent_videos):
            print(f"    Skipped near-duplicate topic: {topic_str}")
            continue
        composite, breakdown = score_topic_idea(i, sig, history, learnings=state.get("learnings"))
        ideas.append({
            "topic": topic_str,
            "category": i.get("category"),
            "angle": str(i.get("angle", "")).strip(),
            "why_trending": str(i.get("why_trending", "")).strip(),
            "format": i.get("format") if i.get("format") in ("short", "long", "story", "animated") else "short",
            "style": i.get("style"),
            "target_audience": i.get("target_audience", "all_ages"),
            "score": composite,
            "score_breakdown": breakdown,
            "used": False,
        })

    ideas.sort(key=lambda x: -float(x.get("score", 0)))
    state["trends"] = {
        "date": today,
        "ideas": ideas,
        "format_trends": [str(x) for x in data.get("format_trends", [])][:6],
        "title_patterns": [str(x) for x in data.get("title_patterns", [])][:6],
        "signals_summary": {
            "google_terms": sum(len(v) for v in sig["google"].values()),
            "news": len(sig["news"]),
            "reddit": len(sig["reddit"]),
            "yt_suggest": len(sig["yt_suggest"]),
            "wiki": len(sig["wiki"]),
        },
    }
    print(f"  {len(ideas)} scored growth topics ready (top score: {ideas[0]['score'] if ideas else 0}).")


def pick_idea(fmt: str, state: dict):
    all_unused = [i for i in (state.get("trends") or {}).get("ideas", []) if not i.get("used")]
    cands = [i for i in all_unused if i.get("format") == fmt]
    if not cands and fmt == "animated":
        cands = [i for i in all_unused if i.get("format") in ("story", "short")]
    if not cands:
        return None
    cands.sort(key=lambda i: -float(i.get("score", 5)))
    pick = random.choice(cands[:3])
    pick["used"] = True
    return dict(pick)


# ------------------------------------------------------------ performance feedback loop
def update_performance(state: dict) -> None:
    """
    Syncs public Data API stats (views, likes, comments) and updates channel learnings
    + category/style/source weights. Full Analytics API metrics are merged via growth_engine.
    """
    vids = state.get("videos", [])[-100:]
    if not (YT_API_KEY and vids):
        return
    stats_map = {}
    try:
        for i in range(0, len(vids), 50):
            ids = ",".join(v["id"] for v in vids[i : i + 50] if v.get("id"))
            if not ids:
                continue
            for it in _yt("videos", part="statistics", id=ids).get("items", []):
                st = it.get("statistics", {})
                stats_map[it["id"]] = {
                    "views": int(st.get("viewCount", 0)),
                    "likes": int(st.get("likeCount", 0)),
                    "comments": int(st.get("commentCount", 0)),
                }
    except Exception as e:
        print(f"  Performance check failed: {type(e).__name__}")
        return

    now, rows = datetime.now(timezone.utc), []
    for v in vids:
        if v.get("id") not in stats_map:
            continue
        st = stats_map[v["id"]]
        v["views"] = st["views"]
        v["likes"] = st["likes"]
        v["comments"] = st["comments"]
        try:
            age = (now - datetime.fromisoformat(v["ts"])).total_seconds() / 86400
        except Exception:
            continue
        if age >= 2:
            # Weight engagement rate + retention + impressions CTR if synced from Analytics API
            retention_bonus = 1.0 + (float(v.get("avg_view_percentage") or 0) / 100.0)
            ctr_bonus = 1.0 + (float(v.get("ctr") or 0) / 10.0)
            vel = (v["views"] / age) * retention_bonus * ctr_bonus
            rows.append((v, vel))

    if len(rows) < 4:
        return
    overall = sum(s for _, s in rows) / len(rows) or 1.0
    weights = state.setdefault("weights", {})
    for key in ("category", "style", "source"):
        groups = {}
        for v, s in rows:
            if v.get(key):
                groups.setdefault(v[key], []).append(s)
        computed = {
            k: round(min(2.0, max(0.5, (sum(x) / len(x)) / overall)), 2)
            for k, x in groups.items()
            if len(x) >= 2
        }
        if computed:
            weights[key] = computed
    state["weights"] = weights
    print(f"  Performance weights updated from {len(rows)} videos: {weights}")

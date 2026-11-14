# RAPTAR: Organic-Growth AI Video Creation & Publishing System

RAPTAR is an autonomous YouTube & Instagram video creation system engineered for **organic audience growth, retention, CTR optimization, and continuous performance learning**.

---

## 1. System Architecture

```
+-----------------------------------------------------------------------------------------+
|                        AUTONOMOUS AGENT ORCHESTRATOR (server.ts)                        |
|  - Headless Node.js / Express Engine (Port 3000)                                        |
|  - Safety Gate: [Approval Gate] vs. [Autonomous] + Analytics & QC API (/api/analytics)  |
+-----------------------------------------------------------------------------------------+
                                           |
+-----------------------------------------------------------------------------------------+
|                         PYTHON GROWTH & PRODUCTION PIPELINE                             |
|  - trends.py           -> Multi-source research (Google Trends, News, YouTube Search     |
|                           Suggestions, Reddit, Wikipedia, YT Data API) + 7-factor score  |
|  - raptar_agent.py     -> High-retention scripting (0-3s hook, 3-15s curiosity gap,     |
|                           middle pattern interrupts, payoff CTA) + 11-language dubbing  |
|  - growth_engine.py    -> Procedural BGM + sidechain narration ducking, 3-concept CTR    |
|                           thumbnails, 5-title YouTube SEO, 10-factor AI QC evaluator, &   |
|                           YouTube Analytics API v2 channel learning engine              |
|  - make_video.py       -> Adaptive Shorts (1080x1920) & Long-form (1920x1080) FX,       |
|                           inline keyword-highlighted captions, semantic non-repeating    |
|                           stock/AI visual matching + licensing attribution              |
|  - upload_youtube.py   -> Separated Short/Long caps, duplicate & QC gates, thumbnail    |
|                           upload, Analytics feedback loop & publish logs                |
|  - upload_instagram.py -> Instagram Graph API v23.0 Reels publisher                     |
+-----------------------------------------------------------------------------------------+
```

---

## 2. Project Directory Structure

```
.
├── .env.example                     # Environment variables template (no secrets)
├── .github/workflows/daily.yml      # Focused 3x/day growth schedule (animated, long, short)
├── Automated-video-creation/
│   ├── growth_engine.py             # BGM ducking, 3-concept thumbnails, SEO, QC & Analytics AI
│   ├── history.json                 # 300-entry topic anti-repetition memory
│   ├── make_video.py                # Video & audio production pipeline
│   ├── raptar_agent.py              # High-retention scripting & 11-language adaptation
│   ├── requirements.txt             # Python dependencies
│   ├── state.json                   # Channel learnings, weights, used media IDs & publish logs
│   ├── trends.py                    # Multi-source topic research & 7-factor scorer
│   ├── upload_instagram.py          # Instagram Graph API v23.0 Reels uploader
│   └── upload_youtube.py            # YouTube Data API v3 uploader + Analytics API v2 sync
├── metadata.json                    # Project metadata & permissions
├── package.json                     # Node.js dependencies & run scripts
├── requirements.txt                 # Root Python requirements
├── server.ts                        # Headless Express backend & REST API
└── tests/
    ├── verify_raptar.py             # Full Python & Growth Engine verification suite
    └── test_api.ts                  # REST API & HTTP 206 streaming test suite
```

---

## 3. Prerequisites & Setup

* **Node.js** v18+, **Python** v3.10+, **FFmpeg** (with `libx264`, `libass`, `librsvg`), and **Noto fonts** (`fonts-noto-core`, `fonts-noto-cjk`).

```bash
python3 -m pip install -r requirements.txt
npm install
cp .env.example .env
```

---

## 4. Running & Testing

```bash
# Start headless server on port 3000
npm run dev

# Generate a Short / Animated Reel / Long-Form video
cd Automated-video-creation
python3 make_video.py --format short
python3 make_video.py --format animated --lang en
python3 make_video.py --format long

# Offline verification build
OFFLINE_TEST=1 python3 make_video.py --format short

# Run full test suites
cd ..
python3 tests/verify_raptar.py
npx tsx tests/test_api.ts
```

---

## 5. Key Growth & Safety Controls

- **Zero Spam Publishing**: Separated daily caps (`MAX_SHORTS_PER_DAY=2`, `MAX_LONG_PER_DAY=1`) and consistent default channel language (`TARGET_LANGUAGE=en`).
- **Pre-Publish Quality Gate**: Every video is evaluated 1–10 across 10 retention, audio, visual, thumbnail, title, and originality factors before upload.
- **Duplicate & Compliance Protections**: Fuzzy Jaccard anti-repetition for both topic ideation (`trends.py`) and upload verification (`upload_youtube.py`), plus `containsSyntheticMedia: True`.

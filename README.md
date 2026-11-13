# RAPTAR: Autonomous AI Video Creation & Social Media Automation System

RAPTAR is an autonomous AI-operated animated Reels, YouTube Shorts, and Long-Form video creation and social media publishing system. It researches trending topics, writes multi-genre animated/storytelling scripts in **11 languages**, generates AI artwork and vector SVG scenes with 2.5D camera choreography, synthesizes multilingual neural voiceovers and `libass` kinetic subtitles, renders crisp 9:16 Reels/Shorts or 16:9 multi-chapter long-form videos with FFmpeg, and publishes automatically to YouTube and Instagram.

---

## 1. System Architecture

```
+-----------------------------------------------------------------------------------------+
|                        AUTONOMOUS AGENT ORCHESTRATOR (server.ts)                        |
|  - Headless Node.js / Express Engine (Port 3000)                                        |
|  - Gemini 4 Hydrogen Brain (Planning, Fact-Checking, Multilingual Adaptation)           |
|  - Safety Dual Mode Gate: [Full Auto] vs. [Approval Gate]                               |
|  - HTTP 206 Streaming Media Server & Automated Scheduler                                |
+-----------------------------------------------------------------------------------------+
                                           |
                              Subprocess IPC & File Sync
                                           |
+-----------------------------------------------------------------------------------------+
|                            PYTHON ANIMATION & VIDEO PIPELINE                            |
|  - raptar_agent.py     -> Multi-genre persona planner, 11-language dubbing & audit      |
|  - trends.py           -> Market Research (Google Trends, Wikipedia, YouTube signals)   |
|  - make_video.py       -> AI Animation (Gemini SVG + Pollinations + 2.5D Ken Burns),   |
|                           Edge-TTS Neural Voices, libass Subtitles, Multi-Chapter Long  |
|  - upload_youtube.py   -> YouTube Data API v3 Uploader (primary + language variants)    |
|  - upload_instagram.py -> Instagram Graph API v23.0 Reels Uploader (primary + dubs)     |
|  - history.json        -> 300-topic anti-repetition FIFO memory                         |
|  - state.json          -> Dynamic category/style/language performance weights           |
+-----------------------------------------------------------------------------------------+
```

---

## 2. Project Directory Structure

```
.
├── .env.example                     # Environment variables template (no secrets)
├── .gitignore                       # Clean ignore rules (excludes media, tokens, work dirs)
├── .github/
│   └── workflows/
│       └── daily.yml                # 7x/day global schedule (animated, short, story, long)
├── Automated-video-creation/        # Core Python Production Pipeline
│   ├── history.json                 # 300-entry topic anti-repetition blacklist
│   ├── make_video.py                # Video & AI animation assembly engine (FFmpeg, libass)
│   ├── raptar_agent.py              # Multi-language & animated genre autonomous agent
│   ├── requirements.txt             # Python dependencies
│   ├── state.json                   # Strategic weights, language index, uploads & trends
│   ├── trends.py                    # Multi-source trend scraper & feedback loops
│   ├── upload_instagram.py          # Instagram Graph API v23.0 Reels uploader
│   └── upload_youtube.py            # YouTube Data API v3 OAuth uploader
├── metadata.json                    # Project metadata & permissions
├── package.json                     # Node.js dependencies & run scripts
├── requirements.txt                 # Root Python requirements
├── server.ts                        # Headless Express backend & Agent Orchestrator
└── tests/                           # Technical Verification & Audit Suite
    ├── verify_raptar.py             # Python engine, FFmpeg, libass, animation & schema tests
    └── test_api.ts                  # REST API & streaming endpoint test suite
```

---

## 3. Prerequisites & Dependencies

### System Requirements
* **Node.js**: v18.0.0 or higher (v20+ recommended)
* **Python**: v3.10 or higher
* **FFmpeg**: v4.4+ with `libx264`, `libass` (HarfBuzz + FriBidi), and `librsvg` support
* **Multilingual Noto Fonts**: `fonts-noto-core`, `fonts-noto-cjk`, `fonts-dejavu-core`, `fonts-liberation`

### Installing System Dependencies (Debian / Ubuntu)
```bash
sudo apt-get update
sudo apt-get install -y ffmpeg fonts-dejavu-core fonts-liberation fonts-noto-core fonts-noto-cjk
```

---

## 4. Installation & Setup

```bash
python3 -m pip install -r requirements.txt
npm install
cp .env.example .env
```

Key environment variables in `.env`:
* `GEMINI_API_KEY`: Required for autonomous agent planning, vector SVG animation, scriptwriting, and translation.
* `PIXABAY_API_KEY` / `PEXELS_API_KEY`: Optional stock footage fallback.
* `TARGET_LANGUAGE`: `auto` | `en` | `ta` | `hi` | `es` | `fr` | `pt` | `de` | `ja` | `ko` | `ar` | `id`.
* `DUB_LANGUAGES`: Optional comma-separated extra dubbed variants rendered per run (e.g. `ta,hi,es`).
* `YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN`: For YouTube publishing.
* `IG_ACCESS_TOKEN`, `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET`: For Instagram Reels publishing.

---

## 5. Running the Application

### Headless Server (Port 3000)
```bash
npm run dev
```

### Headless Autonomous Video Production (CLI)
```bash
cd Automated-video-creation

# Generate an AI animated Reel / Short (3D myth, 3D cartoon comedy, or anime style)
python3 make_video.py --format animated

# Generate in a specific language (Tamil) + dub extra localized variants (English, Hindi)
python3 make_video.py --format animated --lang ta --dub en,hi

# Generate a 16:9 Long-Form multi-chapter video (5-7 minutes with chapters & thumbnail)
python3 make_video.py --format long

# Generate a video with a custom topic
python3 make_video.py --format animated "Every grain holds the bridge: Tiny squirrel Ramayana story"

# Run offline assembly test (no internet or API keys required)
OFFLINE_TEST=1 python3 make_video.py --format animated --lang ta
```

### Social Media Upload Scripts
```bash
cd Automated-video-creation
python3 upload_youtube.py
python3 upload_instagram.py
```

---

## 6. Running the Technical Verification Suite

```bash
python3 tests/verify_raptar.py
npx tsx tests/test_api.ts
```

---

## 7. Safety & Compliance Guardrails

* **Default Mode: Approval Gate**: By default, `server.ts` stages videos in `ready_for_approval` without publishing until explicitly approved.
* **YouTube Compliance**: Automatically tags generated media with `containsSyntheticMedia: True` and sets `defaultLanguage` / `defaultAudioLanguage`.
* **Instagram Compliance**: Uses Instagram Graph API v23.0 container polling and respects daily upload caps.
* **Rate Limits & Anti-Repetition**: Enforces 300-topic FIFO memory and constant-timebase FFmpeg normalization across multi-chapter renders.


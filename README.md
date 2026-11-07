# RAPTAR: Autonomous AI Video Creation & Social Media Automation System

RAPTAR is an autonomous AI-operated video production and social media publishing platform. It autonomously researches trending topics, formulates viral narrative angles, writes and fact-checks original scripts, generates neural audio and kinetic subtitles, stitches video footage with FFmpeg, publishes to YouTube and Instagram, and continuously optimizes future content strategies based on performance feedback.

---

## 1. System Architecture

```
+-----------------------------------------------------------------------------------------+
|                                    RAPTAR COMMAND CENTER                                |
|         React 19 + Tailwind Dashboard (Live Pipeline, Video Player, Trend Radar)        |
+-----------------------------------------------------------------------------------------+
                                           |
                                  REST APIs / SSE / HTTP 206
                                           |
+-----------------------------------------------------------------------------------------+
|                          AUTONOMOUS AGENT ORCHESTRATOR (server.ts)                       |
|  - Gemini 3.8 Flash Brain (Planning, Fact-Checking, Virality Scoring, Self-Optimization)|
|  - Safety Dual Mode Gate: [Full Auto] vs. [Approval Gate]                                |
|  - HTTP 206 Streaming Media Server for High-Speed Video Scrubbing                       |
|  - Automated 24h Background Creation Scheduler                                          |
+-----------------------------------------------------------------------------------------+
                                           |
                              Subprocess IPC & File Sync
                                           |
+-----------------------------------------------------------------------------------------+
|                          PRESERVED & HARDENED PYTHON PIPELINE                           |
|  - trends.py           -> Market Research (Google Trends, Wikipedia, YouTube signals)   |
|  - make_video.py       -> Scripting, edge-tts Narration, Pixabay/Pexels, FFmpeg Muxing  |
|  - upload_youtube.py   -> YouTube Data API v3 Uploader with synthetic media declaration |
|  - upload_instagram.py -> Instagram Graph API v23.0 Container Polling & Reel Publisher   |
|  - history.json        -> 300-topic anti-repetition FIFO memory                         |
|  - state.json          -> Dynamic category/style performance weights                    |
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
│       └── daily.yml                # Preserved original 5-time daily cron workflow
├── Automated-video-creation/        # Core Python Production Pipeline
│   ├── history.json                 # 300-entry topic anti-repetition blacklist
│   ├── make_video.py                # Video assembly engine (FFmpeg, TTS, captions)
│   ├── requirements.txt             # Python dependencies
│   ├── state.json                   # Strategic weights, uploads, and trend radar cache
│   ├── trends.py                    # Multi-source trend scraper & feedback loops
│   ├── upload_instagram.py          # Instagram Graph API v23.0 Unified Login uploader
│   └── upload_youtube.py            # YouTube Data API v3 OAuth uploader
├── index.html                       # Web application entry point
├── metadata.json                    # Project metadata & permissions
├── package.json                     # Node.js dependencies & run scripts
├── requirements.txt                 # Root Python requirements
├── server.ts                        # Full-stack Express backend & Agent Orchestrator
├── src/                             # Frontend Mission Control Dashboard
│   ├── App.tsx                      # Main dashboard controller
│   ├── types.ts                     # TypeScript definitions
│   ├── index.css                    # Tailwind CSS configuration
│   ├── main.tsx                     # React client bootstrap
│   └── components/
│       ├── Header.tsx               # Top bar (Approval Gate vs Full Auto, cycle timer)
│       ├── AgentStatusBanner.tsx    # 5-stage pipeline progress indicator
│       ├── VideoStudioTab.tsx       # Video gallery, inspector, and review triggers
│       ├── VideoPlayerModal.tsx     # HTML5 media player, tags copy, publish action
│       ├── TrendRadarTab.tsx        # Trend opportunities with AI virality scores
│       ├── AgentMemoryTab.tsx       # Interactive category & style weight multipliers
│       ├── DistributionTab.tsx      # YouTube & Instagram quota meters (0/5, 0/4)
│       ├── LogsTab.tsx              # Filterable agent thought stream & telemetry
│       ├── SettingsTab.tsx          # Neural voice persona & duration configs
│       └── GenerateVideoModal.tsx   # Custom topic / on-demand production dialog
├── tests/                           # Technical Verification & Audit Suite
│   ├── verify_raptar.py             # Python engine, FFmpeg, schema, and API tests
│   └── test_api.ts                  # REST API & streaming endpoint test suite
├── tsconfig.json                    # TypeScript compiler configuration
└── vite.config.ts                   # Vite bundler configuration
```

---

## 3. Prerequisites & Dependencies

### System Requirements
* **Node.js**: v18.0.0 or higher (v20+ recommended)
* **Python**: v3.10 or higher
* **FFmpeg**: v4.4+ with `libx264` and `drawtext` support
* **System TTF Fonts**: `DejaVuSans-Bold` or `LiberationSans-Bold` (auto-detected)

### Installing System Dependencies (Debian / Ubuntu / Oracle Linux)
```bash
sudo apt-get update
sudo apt-get install -y ffmpeg fonts-dejavu-core fonts-liberation
```

---

## 4. Installation & Setup

### Step 1: Install Python Dependencies
```bash
python3 -m pip install -r requirements.txt
```

### Step 2: Install Node.js Dependencies
```bash
npm install
```

### Step 3: Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Open `.env` and fill in your keys:
* `GEMINI_API_KEY`: Required for autonomous agent planning, research, scripting, and fact-checking.
* `PIXABAY_API_KEY`: Optional; supplies stock video footage (gradient visuals used as fallback).
* `YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN`: For YouTube publishing.
* `IG_ACCESS_TOKEN`, `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET`: For Instagram Reels publishing.

---

## 5. Running the Application

### Option A: Launch Full-Stack Mission Control Dashboard (Recommended)
```bash
npm run dev
```
Open your browser at `http://localhost:3000`. The dashboard provides:
* Real-time Agent Mindstream & Telemetry
* Interactive HTML5 video player with subtitle inspection
* Trend radar with AI virality scores (1–10)
* One-click manual approval gate or autonomous scheduling toggle
* Visual weight calibration for categories and styles

### Option B: Headless Autonomous Video Production (CLI)
```bash
# Generate an autonomous Short based on current market trends
cd Automated-video-creation
python3 make_video.py

# Generate a 16:9 Long-Form documentary (5-7 minutes with chapters & thumbnail)
python3 make_video.py --format long

# Generate a video with a custom topic
python3 make_video.py "Why Gold Never Tarnishes"

# Run offline assembly test (no internet or API keys required)
OFFLINE_TEST=1 python3 make_video.py
```

### Option C: Social Media Upload Scripts
```bash
cd Automated-video-creation
# Upload output/video.mp4 to YouTube
python3 upload_youtube.py

# Publish output/video.mp4 to Instagram Reels
python3 upload_instagram.py
```

---

## 6. Running the Technical Verification Suite

Verify all system capabilities locally before deployment:

```bash
# 1. Run Python engine & pipeline tests
python3 tests/verify_raptar.py

# 2. Run REST API & streaming media tests
npx tsx tests/test_api.ts
```

All 9 Python pipeline tests and 7 REST API endpoints should pass cleanly.

---

## 7. How to Safely Merge into Your Original GitHub Repository

Follow this safe Git workflow to review and merge into `https://github.com/TheRaptar/Automated-video-creation-`:

```bash
# 1. Clone your original repository locally
git clone https://github.com/TheRaptar/Automated-video-creation-.git
cd Automated-video-creation-

# 2. Create a dedicated verification branch
git checkout -b feature/raptar-v2-upgrade

# 3. Copy the upgraded project files into your local repository
# (Exclude node_modules, build outputs, work directories, and binary videos)

# 4. Review the staged changes
git status
git diff Automated-video-creation/make_video.py

# 5. Run tests locally to ensure full functionality
python3 tests/verify_raptar.py
npm install
npx tsx tests/test_api.ts

# 6. Commit and push the feature branch to GitHub
git add .
git commit -m "feat(raptar): autonomous AI agent orchestrator, web command center, and verified test suite"
git push -u origin feature/raptar-v2-upgrade

# 7. Open a Pull Request on GitHub to inspect the diff and merge into main
```

---

## 8. Safety & Compliance Guardrails

* **Default Mode: Approval Gate**: By default, the system stages videos in "Ready for Review" mode. It does not publish to live social channels without explicit operator approval.
* **YouTube Compliance**: Automatically tags generated media with `containsSyntheticMedia: True` in snippet status.
* **Instagram Compliance**: Strictly adheres to Instagram Graph API v23.0 container polling and limits posting frequency to 4 Reels/day.
* **Rate Limits & Anti-Repetition**: Enforces 300-topic FIFO memory to prevent topic clashes and duplicate uploads.

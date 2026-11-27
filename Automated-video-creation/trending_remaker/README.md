# Raptar Optional Add-on: Trending-Topic Auto-Remaker (Option 1)

An **independent, optional** module that finds the highest-velocity trending topics via the official YouTube Data API v3 (with automatic zero-key fallback to Google Trends & Wikipedia Top Views), extracts the winning hook archetype and narrative structure **without copying third-party footage or scripts**, and automatically produces a **100% original video**.

Zero existing files (`make_video.py`, `upload_youtube.py`, `upload_instagram.py`, `daily.yml`, `server.ts`) are modified.

## How It Works
1. **Viral Scanner (`scanner.py`)**: Ranks recent trending videos by views/hour velocity, engagement ratio, and recency, deduplicating against your existing `history.json` (read-only) and `trending_remaker_history.json`.
2. **Original Blueprint (`blueprint.py`)**: Extracts the hook archetype (`curiosity_gap`, `contrarian_truth`, `number_countdown`, `how_it_actually_works`, `shocking_comparison`, `story_twist`) and generates a fresh, original topic angle and SEO tags.
3. **Dual Original Engine (`remaker.py`)**:
   - `--engine ai` (default): Runs your existing, unmodified `make_video.py` on the original remake topic.
   - `--engine open_media`: Pulls commercial-safe open-license footage (Pexels, Pixabay, Wikimedia Commons, Internet Archive) verified through `licensed_media.license_gate`, strips 100% of original clip audio (`-an`), and renders an original narrated story with SHA-256 provenance proof.
4. **Opt-In Publishing**: Defaults to `--publish none`. Set `--publish youtube|instagram|both` to hand off to your unmodified `upload_youtube.py` / `upload_instagram.py` (daily limits stay enforced).

## CLI Examples (from `Automated-video-creation/`)
```bash
# Scan & rank top viral topics only (dry-run report)
python -m trending_remaker.cli --regions IN,US --niche science --scan-only

# Produce a 100% original AI animated video on the #1 trending topic (dry-run)
python -m trending_remaker.cli --regions IN,US --engine ai --format animated --publish none

# Produce an original open-license stock video on a trending niche & publish to YouTube
python -m trending_remaker.cli --query "space discoveries" --engine open_media --publish youtube
```

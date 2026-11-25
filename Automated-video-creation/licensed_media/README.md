# Raptar Optional Licensed-Media Add-on

An **independent, optional** video-source downloader, fail-closed license verifier, transformative FFmpeg editor, and provenance evidence ledger for Raptar.

This add-on does **not** modify or interfere with your existing `make_video.py`, `upload_youtube.py`, `upload_instagram.py`, `daily.yml` cron schedule, or dashboard (`server.ts`).

---

## Core Compliance & Safety Guarantees

1. **Fail-Closed License Gate (`license_gate.py`)**
   - Only commercial-safe, derivative-safe licenses pass: `PEXELS`, `PIXABAY`, `CC0-1.0`, `PUBLIC-DOMAIN`, `CC-BY-4.0` / `CC-BY-3.0`, `SELF-OWNED`, `WRITTEN-CREATOR-LICENSE`, and `VERIFIED-CC-BY`.
   - Automatically **rejects** `NC` (Non-Commercial), `ND` (No-Derivatives), All Rights Reserved, Fair Use claims, expired permissions, missing `proof_ref`, and raw third-party YouTube/Instagram/TikTok scraping URLs.
   - `download_verified_asset()` raises `PermissionError` if called on any asset that has not passed verification.
2. **Official Open-License APIs & Authorized Creator Sources (`sources.py`)**
   - **Open APIs**: Pexels, Pixabay, Wikimedia Commons (CC0 / Public Domain / CC-BY), Internet Archive (Public Domain / CC0), plus Openverse & Freesound (`CC0`/`CC-BY`) audio.
   - **Authorized YouTube & Instagram**:
     - **Permission Manifest JSON** (`--mode manifest` / `hybrid`) for your own YouTube Studio exports, creator-supplied local/cloud files, or own Instagram Graph media IDs with documented `proof_ref`.
     - **Own-Account Instagram Graph API** (`--mode own_ig`) querying strictly your own account (`/{ig_id}/media`), zero third-party scraping.
     - Optional **YouTube Data API v3** (`--verify-youtube-api`) ownership / Creative Commons metadata cross-verification.
3. **100% Audio Replacement & Transformative FFmpeg Editing (`editor.py`)**
   - Every source clip is explicitly stripped of original audio (`-an`) to prevent Content ID bleed.
   - Rebuilds the video into an original narrated story with multilingual Edge-TTS voiceover, verified `CC0`/`CC-BY` or copyright-free procedural music, kinetic safe-zone ASS captions, peak-frame thumbnail selection, and auto-embedded `CC-BY` attribution credits in YouTube descriptions & Instagram captions.
4. **Immutable Provenance & Evidence Ledger (`ledger.py`)**
   - Records SHA-256 hashes of all input clips and the final rendered MP4 in `licensed_media_ledger.json`, and generates per-video `evidence_certificate.json` and `CREDITS_AND_PROOF.txt`.
5. **Opt-In Uploader Handoff**
   - Defaults to `--publish none` (safe dry-run). When explicitly set to `youtube`, `instagram`, or `both`, hands off `video.mp4`, `metadata.json`, and `thumbnail.jpg` to your existing, unmodified `upload_youtube.py` and `upload_instagram.py` (preserving existing daily rate caps).

---

## Quick Usage (Standalone CLI)

Run from inside `Automated-video-creation/`:

### 1. Open-License APIs (Dry-Run Render Only)
```bash
python -m licensed_media.cli \
  --mode open \
  --query "deep ocean wildlife" \
  --topic "Hidden Secrets of the Deep Ocean" \
  --sources pexels,pixabay,wikimedia,archive \
  --format short \
  --aspect 9:16 \
  --lang en \
  --publish none
```

### 2. Verify-Only Audit on a Permission Manifest
```bash
python -m licensed_media.cli \
  --mode manifest \
  --manifest licensed_media/permission_manifest.example.json \
  --verify-only
```

### 3. Own-Account Instagram Graph API + Openverse CC0/CC-BY Music
```bash
python -m licensed_media.cli \
  --mode own_ig \
  --topic "Behind the Scenes Story" \
  --music openverse \
  --publish none
```

### 4. Hybrid Mode with Explicit Opt-In Upload to YouTube & Instagram
```bash
python -m licensed_media.cli \
  --mode hybrid \
  --manifest my_permissions.json \
  --query "mountain sunrise" \
  --topic "How Dawn Transforms the Himalayas" \
  --publish both
```

---

## Optional Manual GitHub Actions Workflow

Trigger **Licensed Media Add-on (Manual Only)** from the GitHub Actions tab (`workflow_dispatch` only — **no cron schedule**). By default, `publish` is set to `none` so every run produces a downloadable video + `evidence_certificate.json` + `CREDITS_AND_PROOF.txt` artifact for review before publishing.

# Raptar Optional Add-on: Licensed Creator & CC-BY Discovery (Option 3)

An **independent, optional** module that discovers and ranks the most-viewed **explicitly licensed** (`CC-BY`, `CC0`, `Public Domain`, and creator-approved) media across official APIs, produces transformative commentary videos with 100% original audio replacement (`-an`) and auto-embedded attribution credits, and integrates optionally with your unmodified YouTube and Instagram uploaders.

## Compliance & Architecture
- **YouTube Creative Commons (`CC-BY`) Discovery**: Queries official YouTube Data API v3 (`videoLicense=creativeCommon&order=viewCount`) and double-verifies `status.license == "creativeCommon"` on every video. Exports a structured `cc_by_manifest.json` + verified attribution lines (never scrapes `youtube.com/watch`).
- **Popularity-Ranked Open-License Video Discovery**: Ranks Internet Archive Public Domain/CC0/CC-BY items by `downloads desc`, plus Wikimedia Commons, Pexels, Pixabay, and creator Permission Manifests — all gated by fail-closed `licensed_media.license_gate`.
- **Transformative Commentary & Evidence**: Strips 100% of original audio (`-an`), adds original commentary narration, safe-zone captions, copyright-free/licensed music, SHA-256 `ProvenanceLedger` entries, `evidence_certificate.json`, `CREDITS_AND_PROOF.txt`, and auto-embedded CC-BY credits in YouTube descriptions & Instagram captions.

## CLI Examples (from `Automated-video-creation/`)
```bash
# Discover & rank most-viewed CC-BY + open-license clips (report + manifest export only)
python -m cc_discovery.cli --query "space exploration" --discover-only --export-manifest cc_manifest.json

# Produce a transformative commentary video from top-ranked verified clips (dry-run)
python -m cc_discovery.cli --query "ocean wildlife" --sources youtube_cc,archive,wikimedia,pexels --publish none

# Combine creator-approved manifest + CC-BY discovery and publish to YouTube & Instagram
python -m cc_discovery.cli --query "wildlife documentary" --manifest my_creators.json --publish both
```

"""
Comprehensive verification suite for both optional primary modules:
  - Option 1: Trending-Topic Auto-Remaker (`trending_remaker`)
  - Option 3: Licensed Creator & CC-BY Discovery (`cc_discovery`)

Verifies:
  1. Viral trend velocity scoring, YouTube Data API v3 scanning (mocked), zero-key
     fallback, and history deduplication without touching existing history.json.
  2. Original Remake Blueprint generation (never copies source title verbatim).
  3. Real FFmpeg E2E remake via `open_media` engine + `trending_remaker_history.json`
     + CLI `--scan-only` smoke test.
  4. YouTube CC-BY double-verification (strictly rejects standard `youtube` license
     even if returned by search), popularity-ranked Internet Archive discovery,
     and CC-BY manifest template export (zero raw scraping URLs).
  5. Real FFmpeg E2E transformative CC-BY commentary video with automatic CC-BY
     attribution in YouTube & Instagram SEO + compatibility with unmodified
     `upload_youtube.build_body` & `upload_instagram.build_caption` + CLI smoke test.
  6. Both manual-only GitHub Actions workflows have ZERO cron schedules & default `publish: none`.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
APP_DIR = REPO_ROOT / "Automated-video-creation"
sys.path.insert(0, str(APP_DIR))

from cc_discovery.cli import main as cc_cli_main
from cc_discovery.commentary import produce_cc_commentary_video
from cc_discovery.discover import (
    RankedCCReference,
    RankedLicensedClip,
    discover_archive_most_popular,
    discover_youtube_cc_by_most_viewed,
    export_cc_by_manifest_template,
)
from licensed_media.ledger import compute_sha256
from licensed_media.license_gate import VerifiedAsset, verify_asset_license
from trending_remaker.blueprint import build_remake_blueprint, detect_hook_archetype
from trending_remaker.cli import main as remaker_cli_main
from trending_remaker.remaker import run_remake
from trending_remaker.scanner import (
    compute_viral_score,
    discover_viral_signals,
    scan_youtube_most_popular,
    scan_youtube_niche_top,
)


class _FakeResponse:
    def __init__(self, payload: Any, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code
        self.ok = 200 <= status_code < 300

    def json(self) -> Any:
        return self._payload


def _make_synthetic_clip(dst: Path, color: str = "navy", duration: int = 3) -> Path:
    subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-f", "lavfi", "-i", f"color=c={color}:s=640x360:r=24:d={duration}",
            "-f", "lavfi", "-i", f"sine=frequency=1000:sample_rate=44100:duration={duration}",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k",
            "-shortest", str(dst),
        ],
        check=True,
    )
    return dst


def test_option1_viral_scanner_and_blueprint() -> None:
    print("[1/6] Testing Option 1: Viral scanner ranking, deduplication & original blueprint...")
    recent_iso = (datetime.now(timezone.utc) - timedelta(hours=6)).strftime("%Y-%m-%dT%H:%M:%SZ")
    old_iso = (datetime.now(timezone.utc) - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")

    fast = compute_viral_score(300_000, 20_000, 1_500, recent_iso, is_short_form=True)
    stale = compute_viral_score(300_000, 2_000, 100, old_iso, is_short_form=False)
    assert fast["viral_score"] > stale["viral_score"], "Recent high-velocity short must outrank stale clip"

    def _yt_mock(url: str, **kw: Any) -> _FakeResponse:
        if "/search" in url:
            return _FakeResponse({"items": [{"id": {"videoId": "v_fast"}}, {"id": {"videoId": "v_slow"}}]})
        return _FakeResponse({
            "items": [
                {
                    "id": "v_fast",
                    "snippet": {
                        "title": "Why Deep Sea Anglerfish Glow in Pitch Black Water #shorts",
                        "channelTitle": "OceanLab",
                        "publishedAt": recent_iso,
                        "categoryId": "28",
                        "tags": ["ocean", "anglerfish", "bioluminescence"],
                    },
                    "statistics": {"viewCount": "850000", "likeCount": "62000", "commentCount": "3100"},
                    "contentDetails": {"duration": "PT42S"},
                },
                {
                    "id": "v_slow",
                    "snippet": {
                        "title": "5 Surprising Facts About Saturn Rings",
                        "channelTitle": "AstroHub",
                        "publishedAt": old_iso,
                        "categoryId": "28",
                        "tags": ["saturn", "space"],
                    },
                    "statistics": {"viewCount": "120000", "likeCount": "3000", "commentCount": "120"},
                    "contentDetails": {"duration": "PT8M10S"},
                },
            ]
        })

    pop = scan_youtube_most_popular(regions=["US"], niche="science", api_key="fake-yt", http_get=_yt_mock)
    assert len(pop) == 2

    niche = scan_youtube_niche_top(query="ocean", days=7, api_key="fake-yt", http_get=_yt_mock)
    assert len(niche) == 2

    with tempfile.TemporaryDirectory() as td:
        hist_path = Path(td) / "remaker_hist.json"
        # Pre-seed v_slow as already remade so deduplication filters it out
        hist_path.write_text(json.dumps({
            "schema_version": "1.0",
            "entries": [{"source_title": "5 Surprising Facts About Saturn Rings"}],
        }), encoding="utf-8")

        ranked = discover_viral_signals(
            regions=["US"], query="ocean", api_key="fake-yt",
            remaker_history_path=hist_path, http_get=_yt_mock,
        )
        assert len(ranked) == 1 and ranked[0].title.startswith("Why Deep Sea Anglerfish")

        bp = build_remake_blueprint(ranked[0], offline=True)
        assert detect_hook_archetype(ranked[0].title) == "how_it_actually_works"
        assert bp.original_title.lower() != ranked[0].title.lower(), "Remake title MUST be original, never verbatim copy"
        assert bp.recommended_format == "short" and bp.recommended_aspect == "9:16"
        assert len(bp.visual_keywords) >= 2

    print("  PASS: Viral velocity ranking, deduplication, and original blueprint generation passed.")


def test_option1_open_media_ffmpeg_e2e_and_cli() -> None:
    print("[2/6] Testing Option 1: Real FFmpeg E2E open_media remake + CLI --scan-only...")
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        clip = _make_synthetic_clip(td_path / "broll_ocean.mp4", color="darkblue", duration=3)
        asset = VerifiedAsset(
            asset_id="px_ocean_1", media_type="video", source_provider="pexels", external_id="1",
            title="Deep Ocean Waves", creator="Pexels Artist", source_url="https://pexels.com/video/1",
            download_url="https://videos.pexels.com/1.mp4", local_path=str(clip),
            license_code="PEXELS", permission_type="open_api",
            allow_commercial=True, allow_derivatives=True, sha256=compute_sha256(clip),
        )
        assert verify_asset_license(asset).approved

        signals = discover_viral_signals(query="Bioluminescent Ocean Mystery", offline=True)
        bp = build_remake_blueprint(signals[0], fmt="short", aspect="9:16", offline=True)

        out_dir = td_path / "remaker_out"
        ledger_path = td_path / "remaker_ledger.json"
        hist_path = td_path / "remaker_history.json"

        res = run_remake(
            blueprint=bp,
            engine="open_media",
            out_dir=out_dir,
            ledger_path=ledger_path,
            history_path=hist_path,
            publish_target="none",
            offline=True,
            preverified_videos=[asset],
        )
        assert res["engine"] == "open_media"
        assert Path(res["blueprint"]).exists()
        assert Path(res["production"]["video"]).exists()
        assert Path(res["production"]["evidence_certificate"]).exists()
        assert hist_path.exists()
        hist_data = json.loads(hist_path.read_text(encoding="utf-8"))
        assert len(hist_data["entries"]) == 1

        rc = remaker_cli_main(["--query", "Quantum Levitation", "--scan-only", "--offline"])
        assert rc == 0

    print("  PASS: Option 1 FFmpeg E2E open_media remake and CLI --scan-only passed.")


def test_option3_youtube_cc_double_verification_and_archive_ranking() -> None:
    print("[3/6] Testing Option 3: YouTube CC-BY strict double-check & Archive downloads ranking...")

    def _yt_cc_mock(url: str, **kw: Any) -> _FakeResponse:
        if "/search" in url:
            assert kw["params"].get("videoLicense") == "creativeCommon"
            return _FakeResponse({"items": [{"id": {"videoId": "cc_top"}}, {"id": {"videoId": "not_cc"}}]})
        return _FakeResponse({
            "items": [
                {
                    "id": "cc_top",
                    "snippet": {
                        "title": "ISS Orbiting Earth Time-Lapse 4K",
                        "channelTitle": "NASA Open Media",
                        "channelId": "UC_NASA",
                        "publishedAt": "2026-11-20T00:00:00Z",
                        "tags": ["space", "earth", "nasa"],
                    },
                    "statistics": {"viewCount": "2400000", "likeCount": "140000", "commentCount": "4500"},
                    "status": {"license": "creativeCommon"},
                },
                {
                    "id": "not_cc",
                    "snippet": {
                        "title": "Standard Copyrighted Space Video",
                        "channelTitle": "Locked Studio",
                        "channelId": "UC_LOCKED",
                    },
                    "statistics": {"viewCount": "9900000", "likeCount": "500000", "commentCount": "12000"},
                    "status": {"license": "youtube"},
                },
            ]
        })

    cc_refs = discover_youtube_cc_by_most_viewed("space", api_key="fake-yt", http_get=_yt_cc_mock)
    assert len(cc_refs) == 1, "Must strictly drop standard 'youtube' license even if search returned it"
    assert cc_refs[0].video_id == "cc_top"
    assert "CC-BY" in cc_refs[0].attribution_line and "NASA Open Media" in cc_refs[0].attribution_line

    # Verify exported manifest template has zero raw scraping download_url
    with tempfile.TemporaryDirectory() as td:
        m_path = export_cc_by_manifest_template(cc_refs, Path(td) / "cc_manifest.json")
        m_data = json.loads(m_path.read_text(encoding="utf-8"))
        assert len(m_data["assets"]) == 1
        assert "download_url" not in m_data["assets"][0]
        assert m_data["assets"][0]["permission_type"] == "verified_cc_by"

    # Internet Archive ranked by downloads desc (blocks NC)
    def _ia_mock(url: str, **kw: Any) -> _FakeResponse:
        if "advancedsearch.php" in url:
            return _FakeResponse({
                "response": {
                    "docs": [
                        {"identifier": "apollo_pd", "title": "Apollo 11 Moonwalk", "creator": "NASA", "licenseurl": "https://creativecommons.org/publicdomain/mark/1.0/", "downloads": 950000},
                        {"identifier": "blocked_nc", "title": "NC Film", "creator": "Anon", "licenseurl": "https://creativecommons.org/licenses/by-nc/4.0/", "downloads": 5000000},
                    ]
                }
            })
        return _FakeResponse({"files": [{"name": "apollo_11.mp4", "length": "42.0"}]})

    ia_clips = discover_archive_most_popular("apollo", limit=4, http_get=_ia_mock)
    assert len(ia_clips) == 1 and ia_clips[0].asset.external_id == "apollo_pd"
    assert ia_clips[0].popularity_metric == 950000

    print("  PASS: YouTube CC-BY double verification, manifest export, and Archive ranking passed.")


def test_option3_commentary_ffmpeg_e2e_and_uploader_compat() -> None:
    print("[4/6] Testing Option 3: Real FFmpeg CC-BY commentary E2E, auto-attribution & uploader compat...")
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        clip1 = _make_synthetic_clip(td_path / "space_clip.mp4", color="midnightblue", duration=3)
        asset = VerifiedAsset(
            asset_id="wm_space_1", media_type="video", source_provider="wikimedia", external_id="File:Orbit.webm",
            title="Earth Horizon Orbit", creator="ESA Open Archive",
            source_url="https://commons.wikimedia.org/wiki/File:Orbit.webm",
            download_url="https://upload.wikimedia.org/Orbit.webm", local_path=str(clip1),
            license_code="CC-BY-4.0", permission_type="open_api",
            allow_commercial=True, allow_derivatives=True, sha256=compute_sha256(clip1),
        )
        assert verify_asset_license(asset).approved

        ranked_clip = RankedLicensedClip(
            asset=asset, popularity_metric=500_000, popularity_score=91.5, ranking_reason="Wikimedia CC-BY-4.0",
        )
        cc_ref = RankedCCReference(
            video_id="cc_top", title="ISS Orbiting Earth 4K", channel_title="NASA Open Media",
            channel_id="UC_NASA", source_url="https://www.youtube.com/watch?v=cc_top",
            published_at="2026-11-20T00:00:00Z", view_count=2_400_000, like_count=140_000,
            comment_count=4_500, license_status="creativeCommon",
            attribution_line='"ISS Orbiting Earth 4K" by NASA Open Media (CC-BY-3.0 / YouTube Creative Commons) — https://www.youtube.com/watch?v=cc_top',
            popularity_score=96.0,
        )

        out_dir = td_path / "cc_out"
        ledger_path = td_path / "cc_ledger.json"
        res = produce_cc_commentary_video(
            query="space exploration",
            ranked_clips=[ranked_clip],
            yt_cc_refs=[cc_ref],
            fmt="short",
            aspect="9:16",
            out_dir=out_dir,
            ledger_path=ledger_path,
            publish_target="none",
            offline=True,
        )
        prod = res["production"]
        assert Path(prod["video"]).exists() and Path(prod["evidence_certificate"]).exists()
        meta = json.loads(Path(prod["metadata"]).read_text(encoding="utf-8"))
        # Must carry BOTH clip attribution (ESA Open Archive) AND CC-BY commentary reference (NASA Open Media)
        assert "ESA Open Archive" in meta["youtube_seo"]["description"]
        assert "NASA Open Media" in meta["youtube_seo"]["description"]
        assert "NASA Open Media" in meta["instagram_seo"]["caption"]

        # Verify unmodified upload_youtube.py & upload_instagram.py accept metadata cleanly
        import upload_instagram
        import upload_youtube

        yt_body = upload_youtube.build_body(meta, synthetic=True)
        assert "NASA Open Media" in yt_body["snippet"]["description"]
        ig_cap = upload_instagram.build_caption(meta)
        assert "NASA Open Media" in ig_cap and len(ig_cap) <= 2200

    print("  PASS: Option 3 FFmpeg E2E commentary render, dual attribution & uploader compat passed.")


def test_option3_cli_discover_and_offline_manifest() -> None:
    print("[5/6] Testing Option 3: Standalone CLI (--discover-only and offline manifest render)...")
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        clip = _make_synthetic_clip(td_path / "creator_clip.mp4", color="darkslategray", duration=2)
        manifest_path = td_path / "creator_manifest.json"
        manifest_path.write_text(json.dumps({
            "schema_version": "1.0",
            "assets": [{
                "asset_id": "creator_cc_1",
                "media_type": "video",
                "platform": "direct_file",
                "title": "Creator Licensed Clip",
                "creator_name": "Open Filmmaker",
                "source_url": "https://example.com/open-filmmaker",
                "local_path": str(clip),
                "license_code": "CC-BY-4.0",
                "permission_type": "written_creator_license",
                "proof_ref": "Written CC-BY release #2026",
                "allow_commercial": True,
                "allow_derivatives": True,
            }],
        }), encoding="utf-8")

        rc_disc = cc_cli_main(["--query", "filmmaking", "--manifest", str(manifest_path), "--discover-only", "--offline"])
        assert rc_disc == 0

        out_dir = td_path / "cc_cli_out"
        ledger_path = td_path / "cc_cli_ledger.json"
        rc_render = cc_cli_main([
            "--query", "filmmaking",
            "--manifest", str(manifest_path),
            "--out-dir", str(out_dir),
            "--ledger", str(ledger_path),
            "--publish", "none",
            "--offline",
        ])
        assert rc_render == 0
        assert list(out_dir.rglob("video.mp4"))
        assert list(out_dir.rglob("evidence_certificate.json"))

    print("  PASS: Option 3 CLI discover-only and offline commentary render passed.")


def test_manual_workflows_have_zero_cron() -> None:
    print("[6/6] Verifying both optional GitHub Actions workflows have ZERO cron schedules...")
    for wf_name in ("trending_remaker_manual.yml", "cc_discovery_manual.yml"):
        text = (REPO_ROOT / ".github" / "workflows" / wf_name).read_text(encoding="utf-8")
        assert "workflow_dispatch:" in text, f"{wf_name} must use workflow_dispatch"
        assert "\n  schedule:" not in text and "cron:" not in text, f"{wf_name} MUST NOT have any cron schedule!"
        assert "default: none" in text, f"{wf_name} publish input MUST default to none"
    print("  PASS: Both optional manual workflows verified (workflow_dispatch only, zero cron, publish=none default).")


if __name__ == "__main__":
    test_option1_viral_scanner_and_blueprint()
    test_option1_open_media_ffmpeg_e2e_and_cli()
    test_option3_youtube_cc_double_verification_and_archive_ranking()
    test_option3_commentary_ffmpeg_e2e_and_uploader_compat()
    test_option3_cli_discover_and_offline_manifest()
    test_manual_workflows_have_zero_cron()
    print("\nALL 6 OPTION 1 + OPTION 3 VERIFICATION SUITES PASSED!")

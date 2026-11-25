"""
Standalone verification suite for the Optional Licensed-Media Add-on.
Tests fail-closed LicenseGate, all official open-license & authorized source
adapters, real FFmpeg transformative editing (-an audio replacement, captions,
peak cover, attribution injection), existing uploader compatibility, provenance
ledger persistence, and standalone CLI execution.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict

REPO_ROOT = Path(__file__).resolve().parent.parent
APP_DIR = REPO_ROOT / "Automated-video-creation"
sys.path.insert(0, str(APP_DIR))

from licensed_media.cli import main as cli_main
from licensed_media.editor import _normalize_clip_strip_audio, produce_transformative_video
from licensed_media.ledger import ProvenanceLedger, compute_sha256
from licensed_media.license_gate import VerifiedAsset, verify_asset_license
from licensed_media.sources import (
    download_verified_asset,
    fetch_freesound_audio,
    fetch_internet_archive_videos,
    fetch_openverse_audio,
    fetch_own_instagram_videos,
    fetch_pexels_videos,
    fetch_pixabay_videos,
    fetch_wikimedia_commons_videos,
    load_permission_manifest,
    verify_youtube_video_metadata,
)


class _FakeResponse:
    def __init__(self, payload: Any, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code
        self.ok = 200 <= status_code < 300

    def json(self) -> Any:
        return self._payload


def _make_synthetic_clip_with_1khz_tone(dst: Path, color: str = "navy", duration: int = 3) -> Path:
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "lavfi", "-i", f"color=c={color}:s=640x360:r=24:d={duration}",
        "-f", "lavfi", "-i", f"sine=frequency=1000:sample_rate=44100:duration={duration}",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        "-shortest", str(dst),
    ]
    subprocess.run(cmd, check=True)
    return dst


def _probe_streams(path: Path) -> Dict[str, Any]:
    out = subprocess.check_output(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)],
        text=True,
    )
    return json.loads(out)


def test_fail_closed_license_gate() -> None:
    print("[1/5] Testing fail-closed LicenseGate rules...")

    # 1. Approved cases
    valid_cases = [
        VerifiedAsset(
            asset_id="px_1", media_type="video", source_provider="pexels", external_id="1",
            title="Ocean", creator="Jane", source_url="https://pexels.com/video/1",
            download_url="https://videos.pexels.com/video-files/1/hd.mp4",
            license_code="PEXELS", permission_type="open_api",
            allow_commercial=True, allow_derivatives=True,
        ),
        VerifiedAsset(
            asset_id="wm_ccby", media_type="video", source_provider="wikimedia", external_id="2",
            title="Earth Orbit", creator="NASA/ESA", source_url="https://commons.wikimedia.org/wiki/File:Earth.webm",
            download_url="https://upload.wikimedia.org/wikipedia/commons/e/ea/Earth.webm",
            license_code="CC BY 4.0", permission_type="open_api",
            allow_commercial=True, allow_derivatives=True,
        ),
        VerifiedAsset(
            asset_id="creator_ok", media_type="video", source_provider="manifest_direct_file", external_id="3",
            title="Collab Shot", creator="Alex Creator", source_url="https://example.com/alex",
            download_url="https://cdn.example.com/licensed/shot.mp4",
            license_code="WRITTEN-CREATOR-LICENSE", permission_type="written_creator_license",
            proof_ref="Signed release #42", allow_commercial=True, allow_derivatives=True,
            expires_at="2099-12-31",
        ),
    ]
    for a in valid_cases:
        dec = verify_asset_license(a)
        assert dec.approved, f"Expected {a.asset_id} to be approved, got: {dec.reason}"
        assert a.verification_status == "approved"
    assert valid_cases[1].attribution_required is True
    assert "CC-BY-4.0" in valid_cases[1].attribution_text

    # 2. Rejected cases (must FAIL CLOSED)
    rejected_cases = [
        ("NC blocked", VerifiedAsset(
            asset_id="bad_nc", media_type="video", source_provider="wikimedia", external_id="10",
            title="NC Clip", creator="Someone", source_url="https://commons.wikimedia.org/wiki/File:X.webm",
            download_url="https://upload.wikimedia.org/x.webm",
            license_code="CC-BY-NC-4.0", permission_type="open_api",
            allow_commercial=True, allow_derivatives=True,
        )),
        ("ND blocked", VerifiedAsset(
            asset_id="bad_nd", media_type="video", source_provider="wikimedia", external_id="11",
            title="ND Clip", creator="Someone", source_url="https://commons.wikimedia.org/wiki/File:Y.webm",
            download_url="https://upload.wikimedia.org/y.webm",
            license_code="CC-BY-ND-4.0", permission_type="open_api",
            allow_commercial=True, allow_derivatives=True,
        )),
        ("All rights reserved blocked", VerifiedAsset(
            asset_id="bad_arr", media_type="video", source_provider="manifest_direct_file", external_id="12",
            title="Movie", creator="Studio", source_url="https://example.com",
            download_url="https://cdn.example.com/movie.mp4",
            license_code="ALL-RIGHTS-RESERVED", permission_type="written_creator_license",
            proof_ref="none", allow_commercial=True, allow_derivatives=True,
        )),
        ("Expired permission blocked", VerifiedAsset(
            asset_id="bad_exp", media_type="video", source_provider="manifest_direct_file", external_id="13",
            title="Old Clip", creator="Creator", source_url="https://example.com",
            download_url="https://cdn.example.com/old.mp4",
            license_code="WRITTEN-CREATOR-LICENSE", permission_type="written_creator_license",
            proof_ref="Signed PDF", allow_commercial=True, allow_derivatives=True,
            expires_at="2020-01-01",
        )),
        ("Missing proof_ref blocked", VerifiedAsset(
            asset_id="bad_proof", media_type="video", source_provider="manifest_youtube", external_id="14",
            title="No Proof", creator="Creator", source_url="https://youtube.com/watch?v=abc",
            download_url="https://cdn.example.com/clip.mp4",
            license_code="WRITTEN-CREATOR-LICENSE", permission_type="written_creator_license",
            proof_ref="", allow_commercial=True, allow_derivatives=True,
        )),
        ("Raw YouTube scraping URL blocked", VerifiedAsset(
            asset_id="bad_yt_scrape", media_type="video", source_provider="manifest_youtube", external_id="15",
            title="YT Scrape", creator="Other", source_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            download_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            license_code="SELF-OWNED", permission_type="self_owned",
            proof_ref="Claimed", allow_commercial=True, allow_derivatives=True,
        )),
        ("Raw Instagram scraping URL blocked", VerifiedAsset(
            asset_id="bad_ig_scrape", media_type="video", source_provider="manifest_instagram", external_id="16",
            title="IG Scrape", creator="Other", source_url="https://www.instagram.com/reel/ABC123/",
            download_url="https://www.instagram.com/reel/ABC123/",
            license_code="SELF-OWNED", permission_type="self_owned",
            proof_ref="Claimed", allow_commercial=True, allow_derivatives=True,
        )),
        ("Non-commercial flag blocked", VerifiedAsset(
            asset_id="bad_comm", media_type="video", source_provider="pexels", external_id="17",
            title="No Comm", creator="Jane", source_url="https://pexels.com/17",
            download_url="https://videos.pexels.com/17.mp4",
            license_code="PEXELS", permission_type="open_api",
            allow_commercial=False, allow_derivatives=True,
        )),
    ]
    for label, asset in rejected_cases:
        dec = verify_asset_license(asset)
        assert not dec.approved, f"Expected '{label}' to be REJECTED, but it passed!"
        assert asset.verification_status == "rejected"

    # 3. Downloader must refuse unapproved assets
    with tempfile.TemporaryDirectory() as td:
        try:
            download_verified_asset(rejected_cases[0][1], Path(td))
            raise AssertionError("download_verified_asset MUST raise PermissionError on unapproved assets!")
        except PermissionError:
            pass

    print("  PASS: LicenseGate passed all allowlist & fail-closed rejection checks.")


def test_source_adapters_mocked() -> None:
    print("[2/5] Testing official open-license & authorized source adapters (mocked HTTP)...")

    # Pexels
    px_res = fetch_pexels_videos(
        "ocean", limit=2, api_key="fake-key",
        http_get=lambda url, **kw: _FakeResponse({
            "videos": [{
                "id": 901, "url": "https://www.pexels.com/video/ocean-901/", "duration": 10,
                "user": {"name": "Pexels Artist"},
                "video_files": [{"link": "https://videos.pexels.com/901.mp4", "width": 1080, "height": 1920, "file_type": "video/mp4"}],
            }]
        }),
    )
    assert len(px_res) == 1 and px_res[0].verification_status == "approved"

    # Pixabay
    pb_res = fetch_pixabay_videos(
        "mountain", limit=2, api_key="fake-key",
        http_get=lambda url, **kw: _FakeResponse({
            "hits": [{
                "id": 802, "pageURL": "https://pixabay.com/videos/802/", "tags": "mountain, sunrise",
                "user": "Pixabay Creator", "duration": 12,
                "videos": {"large": {"url": "https://cdn.pixabay.com/802.mp4", "width": 1920, "height": 1080}},
            }]
        }),
    )
    assert len(pb_res) == 1 and pb_res[0].verification_status == "approved"

    # Wikimedia Commons (1 CC-BY passes, 1 CC-BY-NC rejected)
    wm_res = fetch_wikimedia_commons_videos(
        "space", limit=3,
        http_get=lambda url, **kw: _FakeResponse({
            "query": {
                "pages": {
                    "101": {
                        "pageid": 101,
                        "title": "File:Approved_Space.webm",
                        "imageinfo": [{
                            "url": "https://upload.wikimedia.org/wikipedia/commons/a/aa/Approved_Space.webm",
                            "descriptionurl": "https://commons.wikimedia.org/wiki/File:Approved_Space.webm",
                            "mime": "video/webm",
                            "width": 1280, "height": 720, "duration": 8,
                            "extmetadata": {
                                "LicenseShortName": {"value": "CC BY 4.0"},
                                "Artist": {"value": "<a>NASA</a>"},
                            },
                        }],
                    },
                    "102": {
                        "pageid": 102,
                        "title": "File:Blocked_NC.webm",
                        "imageinfo": [{
                            "url": "https://upload.wikimedia.org/wikipedia/commons/b/bb/Blocked_NC.webm",
                            "descriptionurl": "https://commons.wikimedia.org/wiki/File:Blocked_NC.webm",
                            "mime": "video/webm",
                            "width": 1280, "height": 720, "duration": 8,
                            "extmetadata": {
                                "LicenseShortName": {"value": "CC BY-NC 4.0"},
                                "Artist": {"value": "BlockedUser"},
                            },
                        }],
                    },
                }
            }
        }),
    )
    assert len(wm_res) == 1 and wm_res[0].external_id == "101" and wm_res[0].title == "Approved_Space.webm"
    assert wm_res[0].attribution_required is True

    # Internet Archive (Public Domain)
    def _ia_http(url: str, **kw: Any) -> _FakeResponse:
        if "advancedsearch.php" in url:
            return _FakeResponse({
                "response": {"docs": [{"identifier": "nasa_apollo_11", "title": "Apollo 11", "creator": "NASA", "licenseurl": "https://creativecommons.org/publicdomain/mark/1.0/"}]}
            })
        return _FakeResponse({"files": [{"name": "apollo11.mp4", "format": "MPEG4", "length": "15.2"}]})

    ia_res = fetch_internet_archive_videos("apollo", limit=2, http_get=_ia_http)
    assert len(ia_res) == 1 and ia_res[0].verification_status == "approved"

    # Openverse Audio (CC0)
    ov_res = fetch_openverse_audio(
        "cinematic", limit=2,
        http_get=lambda url, **kw: _FakeResponse({
            "results": [{
                "id": "ov-1", "title": "Ambient Horizon", "creator": "Open Composer",
                "url": "https://cdn.openverse.org/ov-1.mp3", "foreign_landing_url": "https://openverse.org/audio/ov-1",
                "license": "cc0", "license_version": "1.0", "duration": 60000,
            }]
        }),
    )
    assert len(ov_res) == 1 and ov_res[0].media_type == "audio" and ov_res[0].verification_status == "approved"

    # Freesound Audio (CC-BY)
    fs_res = fetch_freesound_audio(
        "ambient", limit=2, api_key="fs-key",
        http_get=lambda url, **kw: _FakeResponse({
            "results": [{
                "id": 555, "name": "Warm Pad", "username": "SynthLab",
                "url": "https://freesound.org/s/555/",
                "license": "https://creativecommons.org/licenses/by/4.0/",
                "duration": 35.0,
                "previews": {"preview-hq-mp3": "https://cdn.freesound.org/555.mp3"},
            }]
        }),
    )
    assert len(fs_res) == 1 and fs_res[0].attribution_required is True

    # Own-Account Instagram Graph API
    def _ig_http(url: str, **kw: Any) -> _FakeResponse:
        if url.endswith("/me"):
            return _FakeResponse({"id": "178414000000", "username": "theraptar_official"})
        return _FakeResponse({
            "data": [{
                "id": "179001", "caption": "My own reel", "media_type": "VIDEO",
                "media_url": "https://scontent.cdninstagram.com/own_video.mp4",
                "permalink": "https://www.instagram.com/reel/OWN123/",
            }]
        })

    ig_res = fetch_own_instagram_videos(token="fake-ig-tok", ig_id="178414000000", limit=2, http_get=_ig_http)
    assert len(ig_res) == 1 and ig_res[0].source_provider == "own_instagram_api" and ig_res[0].verification_status == "approved"

    # YouTube Data API ownership verification
    ok_own, _ = verify_youtube_video_metadata(
        video_id="vid123", expected_channel_id="UC_OWN", api_key="yt-key",
        http_get=lambda url, **kw: _FakeResponse({
            "items": [{"snippet": {"channelId": "UC_OWN", "channelTitle": "TheRaptar", "title": "My Video"}, "status": {"license": "youtube"}}]
        }),
    )
    assert ok_own is True

    ok_mismatch, _ = verify_youtube_video_metadata(
        video_id="vid999", expected_channel_id="UC_OWN", api_key="yt-key",
        http_get=lambda url, **kw: _FakeResponse({
            "items": [{"snippet": {"channelId": "UC_OTHER", "channelTitle": "Stranger"}, "status": {"license": "youtube"}}]
        }),
    )
    assert ok_mismatch is False

    # Permission Manifest loader (1 approved local clip + 1 rejected scraping clip)
    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        clip = _make_synthetic_clip_with_1khz_tone(td_path / "owned.mp4", color="teal", duration=2)
        manifest_path = td_path / "manifest.json"
        manifest_path.write_text(json.dumps({
            "schema_version": "1.0",
            "assets": [
                {
                    "asset_id": "own_yt_1",
                    "media_type": "video",
                    "platform": "youtube",
                    "title": "My Studio Clip",
                    "creator_name": "TheRaptar",
                    "youtube_video_id": "vid123",
                    "expected_channel_id": "UC_OWN",
                    "source_url": "https://www.youtube.com/watch?v=vid123",
                    "local_path": str(clip),
                    "license_code": "SELF-OWNED",
                    "permission_type": "self_owned",
                    "proof_ref": "YouTube Studio Export",
                    "allow_commercial": True,
                    "allow_derivatives": True,
                },
                {
                    "asset_id": "bad_scrape_2",
                    "media_type": "video",
                    "platform": "youtube",
                    "title": "Scraped Clip",
                    "creator_name": "Someone Else",
                    "source_url": "https://www.youtube.com/watch?v=stolen",
                    "download_url": "https://www.youtube.com/watch?v=stolen",
                    "license_code": "SELF-OWNED",
                    "permission_type": "self_owned",
                    "proof_ref": "None",
                    "allow_commercial": True,
                    "allow_derivatives": True,
                },
            ],
        }), encoding="utf-8")

        approved, rejected = load_permission_manifest(
            manifest_path=manifest_path,
            verify_youtube_api=True,
            yt_api_key="yt-key",
            http_get=lambda url, **kw: _FakeResponse({
                "items": [{"snippet": {"channelId": "UC_OWN", "channelTitle": "TheRaptar", "title": "My Studio Clip"}, "status": {"license": "youtube"}}]
            }),
        )
        assert len(approved) == 1 and approved[0].asset_id == "own_yt_1"
        assert len(rejected) == 1 and rejected[0].asset_id == "bad_scrape_2"

    print("  PASS: All open-license, own-IG, YouTube-API, and manifest adapters passed.")


def test_ffmpeg_transformative_e2e_and_uploader_compat() -> None:
    print("[3/5] Running real FFmpeg transformative E2E test (-an strip, captions, SEO, ledger)...")

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        raw1 = _make_synthetic_clip_with_1khz_tone(td_path / "raw1.mp4", color="navy", duration=3)
        raw2 = _make_synthetic_clip_with_1khz_tone(td_path / "raw2.mp4", color="darkgreen", duration=3)

        # Confirm source clip genuinely has an audio stream before stripping
        src_probe = _probe_streams(raw1)
        assert any(s.get("codec_type") == "audio" for s in src_probe["streams"]), "Source fixture should have audio"

        # Verify _normalize_clip_strip_audio removes 100% of original audio (-an)
        stripped = _normalize_clip_strip_audio(raw1, td_path / "stripped.mp4", 2.5, 720, 1280, 0)
        stripped_probe = _probe_streams(stripped)
        assert not any(s.get("codec_type") == "audio" for s in stripped_probe["streams"]), (
            "Original audio stream MUST be 100% stripped (-an) during clip normalization!"
        )

        # Build two verified assets (1 SELF-OWNED + 1 CC-BY-4.0 requiring attribution)
        a1 = VerifiedAsset(
            asset_id="own_1", media_type="video", source_provider="manifest_youtube", external_id="own1",
            title="My Own Clip", creator="TheRaptar", source_url="https://youtube.com/watch?v=own1",
            local_path=str(raw1), license_code="SELF-OWNED", permission_type="self_owned",
            proof_ref="YouTube Studio Export", allow_commercial=True, allow_derivatives=True,
            sha256=compute_sha256(raw1),
        )
        a2 = VerifiedAsset(
            asset_id="wm_2", media_type="video", source_provider="wikimedia", external_id="File:Nebula.webm",
            title="Carina Nebula", creator="NASA/STScI",
            source_url="https://commons.wikimedia.org/wiki/File:Nebula.webm",
            download_url="https://upload.wikimedia.org/Nebula.webm",
            local_path=str(raw2), license_code="CC-BY-4.0", permission_type="open_api",
            allow_commercial=True, allow_derivatives=True,
            sha256=compute_sha256(raw2),
        )
        assert verify_asset_license(a1).approved
        assert verify_asset_license(a2).approved

        out_dir = td_path / "rendered"
        ledger_path = td_path / "test_ledger.json"

        prod = produce_transformative_video(
            topic="How Ancient Starlight Reaches Earth",
            verified_videos=[a1, a2],
            verified_music=None,
            fmt="short",
            aspect="9:16",
            language="en",
            style="documentary",
            out_dir=out_dir,
            ledger_path=ledger_path,
            offline=True,
        )

        video_file = Path(prod["video"])
        meta_file = Path(prod["metadata"])
        cert_file = Path(prod["evidence_certificate"])
        credits_file = Path(prod["credits_proof_txt"])

        assert video_file.exists() and video_file.stat().st_size > 10_000
        assert meta_file.exists() and cert_file.exists() and credits_file.exists()
        assert ledger_path.exists()

        # Verify output streams & duration
        out_probe = _probe_streams(video_file)
        v_streams = [s for s in out_probe["streams"] if s.get("codec_type") == "video"]
        a_streams = [s for s in out_probe["streams"] if s.get("codec_type") == "audio"]
        assert len(v_streams) == 1 and int(v_streams[0]["width"]) == 1080 and int(v_streams[0]["height"]) == 1920
        assert len(a_streams) == 1
        assert float(out_probe["format"]["duration"]) >= 4.0

        # Verify metadata SEO + auto-embedded CC-BY attribution credits
        meta = json.loads(meta_file.read_text(encoding="utf-8"))
        assert "NASA/STScI" in meta["youtube_seo"]["description"]
        assert "CC-BY-4.0" in meta["youtube_seo"]["description"]
        assert "NASA/STScI" in meta["instagram_seo"]["caption"]
        assert isinstance(meta.get("thumb_offset_ms"), int) and meta["thumb_offset_ms"] >= 0
        assert meta["licensed_media_addon"] is True and meta["original_audio_stripped"] is True

        # Verify compatibility with existing unmodified upload_youtube.py & upload_instagram.py
        import upload_youtube
        import upload_instagram

        yt_body = upload_youtube.build_body(meta, synthetic=True)
        assert yt_body["snippet"]["title"]
        assert "NASA/STScI" in yt_body["snippet"]["description"]

        ig_caption = upload_instagram.build_caption(meta)
        assert "NASA/STScI" in ig_caption
        assert len(ig_caption) <= 2200

        # Verify provenance ledger & mark_published
        ledger = ProvenanceLedger(ledger_path=ledger_path)
        data = ledger.load()
        assert len(data["entries"]) == 1
        entry = data["entries"][0]
        assert entry["record_id"] == prod["record_id"]
        assert entry["output_sha256"] == compute_sha256(video_file)
        assert len(entry["video_sources"]) == 2
        assert ledger.mark_published(prod["record_id"], "youtube", "dry-test") is True
        assert any(t.get("platform") == "youtube" for t in ledger.load()["entries"][0]["publish_targets"])

    print("  PASS: Real FFmpeg E2E render, -an audio strip, SEO/attribution, uploader compat, and ledger passed.")


def test_cli_verify_only_and_offline_manifest() -> None:
    print("[4/5] Testing standalone CLI (--verify-only and --mode manifest --offline --publish none)...")

    with tempfile.TemporaryDirectory() as td:
        td_path = Path(td)
        clip = _make_synthetic_clip_with_1khz_tone(td_path / "cli_clip.mp4", color="purple", duration=2)
        manifest_path = td_path / "cli_manifest.json"
        manifest_path.write_text(json.dumps({
            "schema_version": "1.0",
            "assets": [{
                "asset_id": "cli_own_1",
                "media_type": "video",
                "platform": "direct_file",
                "title": "CLI Owned Clip",
                "creator_name": "TheRaptar",
                "source_url": "https://example.com/own",
                "local_path": str(clip),
                "license_code": "SELF-OWNED",
                "permission_type": "self_owned",
                "proof_ref": "Local master recording",
                "allow_commercial": True,
                "allow_derivatives": True,
            }],
        }), encoding="utf-8")

        rc_verify = cli_main([
            "--mode", "manifest",
            "--manifest", str(manifest_path),
            "--verify-only",
        ])
        assert rc_verify == 0, f"Expected exit 0 from --verify-only, got {rc_verify}"

        out_dir = td_path / "cli_out"
        ledger_path = td_path / "cli_ledger.json"
        rc_render = cli_main([
            "--mode", "manifest",
            "--manifest", str(manifest_path),
            "--topic", "CLI Verified Offline Story",
            "--format", "short",
            "--aspect", "9:16",
            "--out-dir", str(out_dir),
            "--ledger", str(ledger_path),
            "--publish", "none",
            "--offline",
        ])
        assert rc_render == 0, f"Expected exit 0 from offline CLI render, got {rc_render}"
        assert list(out_dir.rglob("video.mp4"))
        assert list(out_dir.rglob("evidence_certificate.json"))
        assert list(out_dir.rglob("CREDITS_AND_PROOF.txt"))
        assert ledger_path.exists()

    print("  PASS: Standalone CLI verify-only and offline render passed.")


def test_workflow_has_no_cron_schedule() -> None:
    print("[5/5] Verifying optional GitHub Actions workflow has ZERO cron schedule triggers...")
    wf_path = REPO_ROOT / ".github" / "workflows" / "licensed_media_manual.yml"
    text = wf_path.read_text(encoding="utf-8")
    assert "workflow_dispatch:" in text, "Workflow must support workflow_dispatch"
    assert "\n  schedule:" not in text and "cron:" not in text, "Manual workflow MUST NOT define any cron schedule!"
    assert "default: none" in text, "Publish input MUST default to 'none'"
    print("  PASS: Manual workflow verified (workflow_dispatch only, zero cron, safe default publish=none).")


if __name__ == "__main__":
    test_fail_closed_license_gate()
    test_source_adapters_mocked()
    test_ffmpeg_transformative_e2e_and_uploader_compat()
    test_cli_verify_only_and_offline_manifest()
    test_workflow_has_no_cron_schedule()
    print("\nALL 5 LICENSED-MEDIA ADD-ON VERIFICATION SUITES PASSED!")

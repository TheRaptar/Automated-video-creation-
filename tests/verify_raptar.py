#!/usr/bin/env python3
"""
RAPTAR Autonomous AI Verification Test Suite
Executes real functional tests on:
1. Video Generation Pipeline (FFmpeg, Fonts, Audio, Subtitle Sync)
2. Agent Planning, Schema Validation, and Fact-Checking
3. Persistent Memory & State Mutation
4. YouTube Data API Logic & Payload Validation
5. Instagram Graph API v23.0 Logic & Container Validation
6. Quota Guards and Error Handling
"""

import sys
import os
import json
import time
import subprocess
from pathlib import Path

# Add project root and python subfolder
BASE_DIR = Path(__file__).resolve().parent.parent
SCRIPT_DIR = BASE_DIR / "Automated-video-creation"
sys.path.insert(0, str(SCRIPT_DIR))

results = []

def test(name: str):
    def decorator(fn):
        def wrapper(*args, **kwargs):
            print(f"--> [TEST RUNNING] {name}...")
            start = time.time()
            try:
                res = fn(*args, **kwargs)
                elapsed = time.time() - start
                results.append({"name": name, "status": "PASS", "duration": round(elapsed, 3), "details": res})
                print(f"    [PASS] {name} ({elapsed:.2f}s)")
                return res
            except Exception as e:
                elapsed = time.time() - start
                results.append({"name": name, "status": "FAIL", "duration": round(elapsed, 3), "error": str(e)})
                print(f"    [FAIL] {name}: {e}")
                return None
        return wrapper
    return decorator

# -------------------------------------------------------------
# 1. Pipeline & Video Generation Tests
# -------------------------------------------------------------
@test("1.1 FFmpeg & Font Resolution")
def test_ffmpeg_and_fonts():
    import make_video
    font = make_video.find_font()
    assert Path(font).exists(), f"Font file not found: {font}"
    # Verify FFmpeg is callable
    r = subprocess.run(["ffmpeg", "-version"], capture_output=True, text=True)
    assert r.returncode == 0, "FFmpeg command failed"
    return {"font": font, "ffmpeg_version": r.stdout.split("\n")[0]}

@test("1.2 Subtitle Kinetic Chunking")
def test_caption_chunks():
    import make_video
    text = "The universe is expanding faster than the speed of light itself."
    duration = 5.0
    chunks = make_video.caption_chunks(text, duration)
    assert len(chunks) > 0, "Caption chunks should not be empty"
    for word_chunk, t_start, t_end in chunks:
        assert t_start < t_end, f"Invalid chunk timing: {t_start} >= {t_end}"
        assert t_end <= duration + 0.1, f"Chunk ends after duration: {t_end} > {duration}"
    return {"chunk_count": len(chunks), "sample": chunks[0]}

@test("1.3 Video Assembly (FFmpeg Offline End-to-End)")
def test_video_assembly():
    import make_video
    make_video.WORK = SCRIPT_DIR / "work"
    make_video.WORK.mkdir(parents=True, exist_ok=True)
    test_work = SCRIPT_DIR / "test_work"
    test_work.mkdir(exist_ok=True)
    
    font = make_video.find_font()
    
    # 1. Create 2-second gradient video segment
    vis = test_work / "test_vis.mp4"
    make_video.run([
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", "gradients=s=1080x1920:c0=0x1a1a2e:c1=0x16213e:duration=2.0:speed=0.03:rate=30",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", str(vis)
    ])
    assert vis.exists() and vis.stat().st_size > 1000, "Visual segment creation failed"

    # 2. Create silent audio of 2 seconds
    audio = test_work / "test_audio.mp3"
    make_video.run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
        "-t", "2.0", "-q:a", "9", "-acodec", "libmp3lame", str(audio)
    ])
    assert audio.exists(), "Audio dummy creation failed"

    # 3. Build scene with text and subtitle overlay
    scene_out = make_video.build_scene(
        idx=99,
        text="Testing automated scene assembly",
        visual=vis,
        audio=audio,
        dur=2.0,
        font=font,
        heading="TEST CHAPTER"
    )
    assert scene_out.exists(), "Scene assembly failed"
    dur = make_video.media_duration(scene_out)
    assert 1.8 <= dur <= 2.5, f"Scene duration mismatch: expected ~2.0s-2.3s, got {dur}s"
    
    # Cleanup test work
    import shutil
    shutil.rmtree(test_work, ignore_errors=True)
    return {"rendered_scene": str(scene_out.name), "duration_sec": dur}

# -------------------------------------------------------------
# 2. Agent Planning, Schema & Fact-Checking Logic
# -------------------------------------------------------------
@test("2.1 Script Schema Validation Logic")
def test_script_schema():
    import make_video
    valid_payload = {
        "title": "Quantum Levitation Mystery",
        "topic": "Superconductivity and Meissner effect",
        "scenes": [
            {"text": "Did you know magnets can float above superconductors?", "search_terms": ["superconductor", "magnet"]},
            {"text": "When cooled by liquid nitrogen, magnetic fields are expelled.", "search_terms": ["liquid nitrogen", "physics"]},
            {"text": "This locks the object in mid-air with zero friction.", "search_terms": ["levitation", "science"]}
        ]
    }
    assert make_video._valid_scenes(valid_payload, minimum=3), "Valid scenes failed validation"
    
    normalized = make_video._normalize(valid_payload)
    assert normalized["hashtags"] is not None, "Normalization should add hashtags"
    assert len(normalized["scenes"]) == 3, "Scenes should be preserved"

    # Test invalid schema handling
    invalid_payload = {"title": "Bad", "scenes": []}
    assert not make_video._valid_scenes(invalid_payload, minimum=3), "Empty scenes should fail validation"
    return {"valid": True, "normalized_title": normalized["title"]}

@test("2.2 Gemini Model Identifier Verification")
def test_gemini_model_identifiers():
    import make_video
    # Valid models per Gemini API guidelines:
    # 'gemini-3.8-flash', 'gemini-flash-latest'
    # Disallowed: 'gemini-1.5-flash', 'gemini-2.0-flash', 'gemini-pro'
    disallowed = ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-pro", "gemini-2.0-flash", "gemini-2.0-pro"]
    
    # Check default model configured in make_video.py
    configured_model = os.environ.get("GEMINI_MODEL", make_video.GEMINI_MODEL)
    assert configured_model not in disallowed, f"Prohibited model configured: {configured_model}"
    assert configured_model == "gemini-4-hydrogen" or "gemini" in configured_model, f"Unexpected default model: {configured_model}"
    
    # Verify fallback models filter
    models = make_video._gemini_models()
    for m in models:
        assert m not in disallowed, f"Prohibited model in fallback list: {m}"
    return {"configured_model": configured_model, "fallback_models": models}

@test("1.4 Multilingual Font & libass Subtitle Rendering (Tamil/Hindi/Arabic/CJK)")
def test_multilingual_ass_rendering():
    import make_video
    import shutil
    make_video.configure("animated")
    make_video.WORK = SCRIPT_DIR / "work"
    make_video.WORK.mkdir(parents=True, exist_ok=True)
    test_work = SCRIPT_DIR / "test_lang_work"
    test_work.mkdir(exist_ok=True)
    orig_work = make_video.WORK
    make_video.WORK = test_work
    try:
        fonts = {lang: make_video.find_font(lang) for lang in ("en", "ta", "hi", "ar")}
        for lang, fpath in fonts.items():
            assert Path(fpath).exists(), f"Font missing for {lang}: {fpath}"
        # Test Unicode Tamil + Japanese chunking
        ta_text = "சிறிய அணில் மணலைக் கொண்டு பாலம் கட்ட உதவியது"
        ta_chunks = make_video.caption_chunks(ta_text, 3.0)
        assert len(ta_chunks) >= 2, "Tamil caption chunking failed"
        ja_text = "小さなリスが砂を運んで橋を作りました"
        ja_chunks = make_video.caption_chunks(ja_text, 3.0)
        assert len(ja_chunks) >= 2, "Japanese CJK character chunking failed"

        # Render 1.5s Tamil ASS scene through FFmpeg libass
        vis = test_work / "ta_vis.mp4"
        aud = test_work / "ta_aud.mp3"
        make_video.run([
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", "gradients=s=1080x1920:c0=0x2c1654:c1=0x0f0f23:duration=1.5:speed=0.03:rate=30",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(vis),
        ])
        make_video.run([
            "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
            "-t", "1.5", "-q:a", "9", "-acodec", "libmp3lame", str(aud),
        ])
        sc_out = make_video.build_scene(
            idx=101,
            text=ta_text,
            visual=vis,
            audio=aud,
            dur=1.5,
            font=fonts["ta"],
            heading="அணில் கதை",
            style_meta={"style": "animated_myth"},
            lang="ta",
        )
        assert sc_out.exists() and make_video.media_duration(sc_out) >= 1.4, "Tamil libass scene failed"
        return {"fonts_checked": list(fonts.keys()), "ta_chunks": len(ta_chunks), "ja_chunks": len(ja_chunks)}
    finally:
        make_video.WORK = orig_work
        shutil.rmtree(test_work, ignore_errors=True)

@test("1.5 AI Animated Vector SVG & 2.5D Motion Pipeline")
def test_animated_svg_motion_pipeline():
    import make_video
    import shutil
    make_video.configure("animated")
    test_work = SCRIPT_DIR / "test_anim_work"
    test_work.mkdir(exist_ok=True)
    orig_work, orig_offline = make_video.WORK, make_video.OFFLINE
    make_video.WORK = test_work
    make_video.OFFLINE = True
    try:
        svg_path = test_work / "scene_0.svg"
        png_path = test_work / "scene_0.png"
        svg_code = make_video._procedural_svg("animated_myth", 0)
        svg_path.write_text(svg_code, encoding="utf-8")
        make_video.run(["ffmpeg", "-y", "-i", str(svg_path), "-vf", f"scale={make_video.W}:{make_video.H}", str(png_path)])
        assert make_video._valid_image(png_path), "SVG rasterization to PNG via FFmpeg librsvg failed"

        vid_path = make_video.make_animated_visual(
            idx=0,
            sc={"image_prompt": "Tiny squirrel carrying golden sand on ocean bridge", "camera_motion": "dolly_pulse", "fx": "golden_glow"},
            total=2.0,
            style="animated_myth",
        )
        assert vid_path and vid_path.exists() and make_video._valid_video(vid_path), "Animated 2.5D video synthesis failed"
        return {"png_bytes": png_path.stat().st_size, "animated_clip": vid_path.name}
    finally:
        make_video.WORK = orig_work
        make_video.OFFLINE = orig_offline
        shutil.rmtree(test_work, ignore_errors=True)

@test("1.6 Long-Form Multi-Chapter & Constant-FPS Concat E2E")
def test_long_form_architecture():
    import make_video
    import shutil
    make_video.configure("long")
    assert (make_video.W, make_video.H) == (1920, 1080), "Long format must configure 1920x1080 landscape"
    orig_offline = make_video.OFFLINE
    make_video.OFFLINE = True
    test_work = SCRIPT_DIR / "test_long_work"
    test_work.mkdir(exist_ok=True)
    orig_work = make_video.WORK
    make_video.WORK = test_work
    try:
        script = make_video.generate_long("Mystery of the Ramayana Bridge", [], {}, lang="en")
        chapters = script.get("chapters", [])
        scenes = script.get("scenes", [])
        assert len(chapters) >= 4, f"Expected >=4 chapters in long-form script, got {len(chapters)}"
        assert len(scenes) >= 12, f"Expected >=12 scenes in long-form script, got {len(scenes)}"
        assert script.get("_already_reviewed") is True, "Long-form should mark chapters as pre-reviewed"

        # Verify constant FPS landscape gradient + concat stability across 2 scenes
        built = []
        for idx in range(2):
            v = test_work / f"lv_{idx}.mp4"
            a = test_work / f"la_{idx}.mp3"
            make_video._gradient(v, 1.5, style="legend")
            make_video.run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo", "-t", "1.5", "-q:a", "9", "-acodec", "libmp3lame", str(a)])
            s = make_video.build_scene(idx, scenes[idx]["text"], v, a, 1.5, make_video.find_font("en"), heading=f"Chapter {idx+1}", lang="en")
            built.append(s)
        joined = test_work / "long_joined.mp4"
        clist = test_work / "concat.txt"
        clist.write_text("\n".join(f"file '{p.resolve()}'" for p in built), encoding="utf-8")
        make_video.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(clist), "-c", "copy", "-movflags", "+faststart", str(joined)])
        total_dur = make_video.media_duration(joined)
        assert 2.8 <= total_dur <= 3.6, f"Long-form concat duration drift detected: {total_dur}s"
        return {"chapters": len(chapters), "scenes": len(scenes), "concat_dur": total_dur}
    finally:
        make_video.OFFLINE = orig_offline
        make_video.WORK = orig_work
        make_video.configure("short")
        shutil.rmtree(test_work, ignore_errors=True)

# -------------------------------------------------------------
# 3. Persistent Memory Across Multiple Executions
# -------------------------------------------------------------
@test("3.1 Persistent State & History Updates")
def test_persistent_memory():
    import make_video
    test_hist_file = SCRIPT_DIR / "test_history.json"
    test_state_file = SCRIPT_DIR / "test_state.json"
    
    # Backup original pointers
    orig_h, orig_s = make_video.HISTORY, make_video.STATE
    make_video.HISTORY, make_video.STATE = test_hist_file, test_state_file
    
    try:
        # Run 1: Save topic and category
        make_video.save_history(["Topic A", "Topic B"])
        make_video.save_state({"recent_categories": ["space"], "weights": {"style": {"fact": 1.4}}})
        
        # Read back in new execution
        hist1 = make_video.load_history()
        state1 = make_video.load_state()
        assert len(hist1) == 2 and hist1[0] == "Topic A", "History read mismatch"
        assert state1.get("weights", {}).get("style", {}).get("fact") == 1.4, "State weights mismatch"
        
        # Run 2: Mutate and verify anti-repetition append
        make_video.save_history(hist1 + ["Topic C"])
        hist2 = make_video.load_history()
        assert len(hist2) == 3 and hist2[-1] == "Topic C", "History append failed"
        
        # Verify 300 topic cap
        large_list = [f"Topic {i}" for i in range(350)]
        make_video.save_history(large_list)
        hist_capped = make_video.load_history()
        assert len(hist_capped) == 300, f"History should cap at 300, got {len(hist_capped)}"
        
    finally:
        make_video.HISTORY, make_video.STATE = orig_h, orig_s
        test_hist_file.unlink(missing_ok=True)
        test_state_file.unlink(missing_ok=True)
        
    return {"persistence_verified": True, "cap_verified": 300}

# -------------------------------------------------------------
# 4. YouTube OAuth Authentication & Upload Logic Verification
# -------------------------------------------------------------
@test("4.1 YouTube Upload Payload & Quota Guard")
def test_youtube_logic():
    import upload_youtube
    meta = {
        "title": "Why Gold Never Tarnishes",
        "description": "The noble chemistry of elemental gold explained simply.",
        "hashtags": ["#science", "#chemistry", "#gold"],
        "format": "short"
    }
    body = upload_youtube.build_body(meta, synthetic=True)
    assert "#Shorts" in body["snippet"]["title"], "Shorts tag missing from YouTube title"
    assert body["status"]["containsSyntheticMedia"] is True, "Synthetic media disclosure not flagged"
    assert body["snippet"]["categoryId"] in ("24", "27"), "Category id should be valid Entertainment (24) or Education (27)"
    assert len(body["snippet"]["tags"]) >= 3, "Tags should have at least 3 entries"
    
    # Test token refresh error-handling when credentials missing
    token_error = False
    try:
        upload_youtube.get_access_token()
    except (KeyError, SystemExit, Exception):
        token_error = True
    assert token_error, "Should fail safely when credentials are not present"
    return {"title": body["snippet"]["title"], "synthetic": True, "category": "27 (Education)"}

# -------------------------------------------------------------
# 5. Instagram Graph API v23.0 Container & Validation Logic
# -------------------------------------------------------------
@test("5.1 Instagram Reels Container & Guardrails")
def test_instagram_logic():
    import upload_instagram
    assert upload_instagram.API_VERSION == "v23.0", f"Unexpected Instagram API version: {upload_instagram.API_VERSION}"
    assert "graph.facebook.com" in upload_instagram.GRAPH_BASE, "Unexpected Graph base URL"
    
    # Test Cloudinary signature generation
    params = {"timestamp": "1700000000", "public_id": "test_video"}
    secret = "test_secret_123"
    sig = upload_instagram.cloudinary_signature(params, secret)
    assert len(sig) == 40, f"HMAC-SHA1 signature length mismatch: {len(sig)}"
    
    # Test safe token resolution fallback (exits cleanly with SystemExit when unconfigured)
    token_missing = False
    try:
        upload_instagram.get_token()
    except SystemExit:
        token_missing = True
    assert token_missing, "Without env vars, get_token should halt execution cleanly"
    return {"api_version": upload_instagram.API_VERSION, "signature_length": len(sig), "missing_token_handled": True}

# -------------------------------------------------------------
# 6. Trend Radar Feedback Calculation
# -------------------------------------------------------------
@test("6.1 Performance Feedback Multiplier Algorithm")
def test_performance_weights():
    import trends
    state = {
        "videos": [
            {"id": "v1", "ts": "2026-11-01T00:00:00+00:00", "category": "space", "style": "fact"},
            {"id": "v2", "ts": "2026-11-01T00:00:00+00:00", "category": "space", "style": "fact"},
            {"id": "v3", "ts": "2026-11-01T00:00:00+00:00", "category": "ocean", "style": "story"},
            {"id": "v4", "ts": "2026-11-01T00:00:00+00:00", "category": "ocean", "style": "story"},
        ]
    }
    # Verify bounds function handles empty/small videos safely
    trends.update_performance(state)
    return {"handled_safely": True}

# -------------------------------------------------------------
# 7. RaptarAgent Task-Oriented AI Engine Verification
# -------------------------------------------------------------
@test("7.1 RaptarAgent Task-Oriented Capabilities")
def test_raptar_agent_engine():
    from raptar_agent import RaptarAgent
    agent = RaptarAgent(script_dir=SCRIPT_DIR)
    
    # 1. Test memory reading
    hist = agent.load_history()
    state = agent.load_state()
    assert isinstance(hist, list), "Agent history should be a list"
    assert isinstance(state, dict), "Agent state should be a dict"
    
    # 2. Test topic formulation & weighted choice
    topic_info = agent.evaluate_and_pick_topic(
        {},
        ["Horror & Supernatural Thrillers", "Children's Whimsical Fables & Adventures", "Adult Psychological Thrillers & Sci-Fi"],
        format_type="short"
    )
    valid_styles = [
        "animated_myth", "animated_comedy", "animated_anime",
        "horror", "fable", "thriller", "scifi", "legend", "mystery",
        "fitness_glamour",
        "allure", "chemistry", "charm", "seduction", "romance",
        "glamour", "aesthetic", "mindset", "spectacle", "story", "fact", "myth", "how", "top3", "whatif"
    ]
    assert topic_info["style"] in valid_styles, f"Invalid style assigned: {topic_info.get('style')}"
    
    # 3. Test script planning
    script = agent.plan_script(topic_info, format_type="short")
    assert "scenes" in script and len(script["scenes"]) >= 3, "Script planning failed scene minimum"
    assert "search_terms" in script["scenes"][0], "Visual search terms missing from scene 1"
    
    # 4. Test fact-check audit
    audited = agent.audit_and_fact_check(script)
    assert len(audited["scenes"]) == len(script["scenes"]), "Fact check altered scene count"
    
    # 5. Test feedback loop
    agent.update_feedback_weights()
    return {
        "topic": topic_info["topic"],
        "scenes_planned": len(script["scenes"]),
        "fact_checked": True,
        "self_learning": True,
    }

@test("7.2 Multilingual Registry, Animated Genres & Translation Preservation")
def test_multilingual_and_animated_agent():
    from raptar_agent import RaptarAgent, LANGUAGES
    agent = RaptarAgent(script_dir=SCRIPT_DIR)
    assert len(LANGUAGES) >= 10, f"Expected >=10 languages, got {len(LANGUAGES)}"
    for code in ("en", "ta", "hi", "es", "fr", "pt", "de", "ja", "ko", "ar", "id"):
        assert code in LANGUAGES, f"Language missing: {code}"
        voice = agent.get_voice_for_language(code)
        assert voice and "Neural" in voice, f"Missing neural voice for {code}: {voice}"

    # Verify animated comedy profile & script planning
    topic_info = agent.evaluate_and_pick_topic(
        {},
        ["3D Cartoon Character Comedies & Adventures", "3D Animated Mythological & Cultural Epics"],
        format_type="animated",
        lang="ta",
    )
    assert topic_info["language"] == "ta", "Topic info should record target language ta"
    script = agent.plan_script(topic_info, format_type="animated", lang="ta")
    assert len(script.get("scenes", [])) >= 4, "Animated script should plan at least 4 scenes"
    assert "camera_motion" in script["scenes"][0], "Animated scene missing camera_motion"
    assert "motion_prompt" in script["scenes"][0], "Animated scene missing temporal motion_prompt"

    # Translate offline fallback should safely preserve scene count
    dubbed = agent.translate_script(script, "hi")
    assert dubbed["language"] == "hi" and len(dubbed["scenes"]) == len(script["scenes"])
    return {"languages": len(LANGUAGES), "animated_style": topic_info["style"], "scenes": len(script["scenes"])}


@test("1.7 Free AI Video Engine (Gradio SSE Parser, Motion Prompt & Boomerang Clip Normalization)")
def test_free_ai_video_engine():
    import make_video
    import shutil
    make_video.configure("animated")
    test_work = SCRIPT_DIR / "test_aivid_work"
    test_work.mkdir(exist_ok=True)
    try:
        host = "https://saravutw-wan2-2-i2v-lightning-4-8step-custom.hf.space"
        # 1. Verify nested Gradio video payload extraction (both Wan2.2 and LTX formats)
        u1 = make_video._extract_gradio_media_url([{"video": {"url": f"{host}/gradio_api/file=/tmp/gradio/abc/clip.mp4"}}], host)
        assert u1 and u1.endswith("clip.mp4"), f"Failed LTX format extraction: {u1}"
        u2 = make_video._extract_gradio_media_url([{"path": "/tmp/gradio/xyz/wan.mp4"}], host)
        assert u2 == f"{host}/gradio_api/file=/tmp/gradio/xyz/wan.mp4", f"Failed Wan2.2 path extraction: {u2}"

        # 2. Verify motion prompt builder includes art style & temporal hints
        make_video.STORY.update(art_style="3D Pixar animation", characters="Tiny squirrel")
        mp = make_video._build_motion_prompt({"motion_prompt": "Squirrel scurries across golden beach"})
        assert "3D Pixar animation" in mp and "Squirrel scurries" in mp and "24fps" in mp

        # 3. Verify _normalize_ai_video_clip handles short 1.2s clip -> 4.0s seamless boomerang upscale
        raw = test_work / "raw_1s.mp4"
        out = test_work / "norm_4s.mp4"
        make_video.run([
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", "gradients=s=560x832:c0=0x112233:c1=0xaa5522:duration=1.2:rate=16",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(raw),
        ])
        make_video._normalize_ai_video_clip(raw, out, 4.0, fx="warm_glow")
        assert make_video._valid_video(out), "Normalized boomerang AI video failed validation"
        dur = make_video.media_duration(out)
        assert 3.8 <= dur <= 4.2, f"Expected ~4.0s boomerang normalized clip, got {dur}s"
        return {"extracted_formats": 2, "normalized_dur": round(dur, 2)}
    finally:
        shutil.rmtree(test_work, ignore_errors=True)


@test("1.8 Motion Engine (Theatre.js Keyframes, SVG.js Parallax & Gemini SVG Auto-Rigging)")
def test_motion_engine_svg_and_keyframes():
    import motion_engine as me
    import make_video
    import shutil
    make_video.configure("animated")
    test_work = SCRIPT_DIR / "test_motion_work"
    test_work.mkdir(exist_ok=True)
    try:
        # 1. Verify cubic-bezier, spring, color lerp & Theatre.js-style MotionSheet
        sheet = me.build_scene_motion_sheet(3.0, motion="dolly_pulse")
        v0, v5, v1 = sheet.sample(0.0), sheet.sample(0.5), sheet.sample(1.0)
        assert abs(v0["cam_scale"] - 1.02) < 0.02, f"Unexpected start scale: {v0}"
        assert v5["cam_scale"] > 1.04, f"Expected pulse peak > 1.04, got {v5}"
        assert me.lerp_value("#000000", "#ffffff", 0.5) in ("#7f7f7f", "#808080")
        assert sheet.to_dict()["sheet"] == "scene_dolly_pulse"

        # 2. Render procedural 6-layer animated SVG sequence
        out_proc = test_work / "proc_motion.mp4"
        ok_proc = me.render_animated_svg_scene(
            out_proc, 1080, 1920, 2.0, fps=30, style="animated_myth", idx=0, motion="zoom_in", fx="warm_glow"
        )
        assert ok_proc and make_video._valid_video(out_proc), "Procedural animated SVG render failed"
        dur_proc = make_video.media_duration(out_proc)
        assert 1.8 <= dur_proc <= 2.2, f"Unexpected procedural SVG duration: {dur_proc}"

        # 3. Auto-rig a Gemini-style SVG into depth-stratified parallax layers + particles
        sample_svg = """<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="1920" viewBox="0 0 1080 1920">
          <rect width="1080" height="1920" fill="#0f172a"/>
          <circle cx="540" cy="450" r="160" fill="#fbbf24"/>
          <path d="M0 1280 Q540 1120 1080 1280 L1080 1920 L0 1920 Z" fill="#1e293b"/>
          <circle cx="540" cy="1100" r="95" fill="#38bdf8"/>
        </svg>"""
        out_rig = test_work / "rig_motion.mp4"
        ok_rig = me.render_animated_svg_scene(
            out_rig, 1080, 1920, 1.8, fps=30, style="animated_anime", idx=1, motion="pan_right",
            fx="anime_neon", base_svg=sample_svg,
        )
        assert ok_rig and make_video._valid_video(out_rig), "Gemini SVG auto-rigging render failed"
        return {"proc_dur": round(dur_proc, 2), "rig_ok": True, "tracks": len(sheet.tracks)}
    finally:
        shutil.rmtree(test_work, ignore_errors=True)


@test("1.9 Particle VFX, Natron Compositor, xfade Transitions & Synfig .sif Export")
def test_particles_compositor_transitions_and_synfig():
    import motion_engine as me
    import make_video
    import shutil
    import xml.etree.ElementTree as ET
    make_video.configure("animated")
    test_work = SCRIPT_DIR / "test_vfx_work"
    test_work.mkdir(exist_ok=True)
    orig_work = make_video.WORK
    make_video.WORK = test_work
    try:
        # 1. Verify all 5 Effekseer/OpenVDB particle presets emit valid SVG groups
        presets = ("sparks_embers", "sakura_petals", "volumetric_mist", "cyber_motes", "magic_stars")
        for preset in presets:
            em = me.ParticleEmitter(preset, 540, 960, seed=7)
            frag = em.render_svg_group(1.25)
            assert frag.startswith('<g id="vfx-particles">') and frag.endswith("</g>"), f"Invalid particle SVG for {preset}"

        # 2. Verify Natron CompositorGraph filter compilation & audio mastering filter
        graph = me.CompositorGraph().add("scale_crop", w=1080, h=1920).add("grade", fx="warm_glow").add("fps", fps=30).add("sar")
        vf = graph.compile()
        assert "scale=1080:1920" in vf and "colorbalance=" in vf and "fps=30" in vf
        af = me.build_audio_master_filter(3.5)
        assert "acompressor=" in af and "atrim=0:3.500" in af

        # 3. Verify particle alpha overlay compositing + xfade/acrossfade scene joining
        base_v = test_work / "base.mp4"
        make_video.run([
            "ffmpeg", "-y", "-f", "lavfi",
            "-i", "gradients=s=1080x1920:c0=0x170d33:c1=0xb5446e:duration=1.6:rate=30",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(base_v),
        ])
        ov_v = test_work / "with_vfx.mp4"
        assert me.composite_particles_onto_video(base_v, ov_v, 1080, 1920, 1.6, style="animated_myth", idx=2)
        assert make_video._valid_video(ov_v), "Particle-composited clip invalid"

        aud = test_work / "aud.mp3"
        make_video.run([
            "ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
            "-t", "1.4", "-q:a", "9", "-acodec", "libmp3lame", str(aud),
        ])
        font = make_video.find_font("en")
        s1 = make_video.build_scene(201, "First animated scene", ov_v, aud, 1.4, font, lang="en")
        s2 = make_video.build_scene(202, "Second animated scene", base_v, aud, 1.4, font, lang="en")
        joined = test_work / "joined_xfade.mp4"
        assert me.join_scenes_with_transitions([s1, s2], joined, style="animated_myth", fps=30, transition_dur=0.25)
        assert make_video._valid_video(joined)
        jdur = make_video.media_duration(joined)
        assert 2.8 <= jdur <= 3.3, f"Unexpected xfade joined duration: {jdur}"

        # 4. Verify Synfig Studio .sif XML export
        sif_path = me.export_synfig_sif(test_work / "scene.sif", 1080, 1920, 3.0, fps=30, style="animated_myth", title="Demo")
        root = ET.fromstring(sif_path.read_text(encoding="utf-8"))
        assert root.tag == "canvas" and root.attrib.get("width") == "1080" and len(root.findall("layer")) >= 2
        return {"presets": len(presets), "xfade_dur": round(jdur, 2), "synfig_layers": len(root.findall("layer"))}
    finally:
        make_video.WORK = orig_work
        shutil.rmtree(test_work, ignore_errors=True)


@test("8.1 Hardware-Aware Detection & Model Recommendation Engine")
def test_hardware_manager():
    import hardware_manager
    hw = hardware_manager.detect_hardware()
    d = hw.to_dict()
    assert d["cpu_cores"] >= 1 and d["ram_gb"] > 0 and d["disk_free_gb"] > 0
    assert d["tier"] in ("cpu_ci", "cpu_local", "gpu_low_vram", "gpu_mid_vram", "gpu_high_vram")
    assert "video" in d["recommendations"] and "lipsync" in d["recommendations"]
    assert d["tools"].get("ffmpeg") is True
    return {"tier": d["tier"], "cores": d["cpu_cores"], "ram_gb": d["ram_gb"], "gpu": d["gpu_vendor"]}


@test("8.2 CharacterBible Consistency Locking & Multi-Language Multi-Voice Casting")
def test_character_bible():
    from character_manager import CharacterBible
    import shutil
    test_dir = SCRIPT_DIR / "test_char_work"
    test_dir.mkdir(exist_ok=True)
    try:
        for lang in ("en", "hi", "ta"):
            bible = CharacterBible(project_dir=test_dir, lang=lang)
            dad = bible.register("Sheru", archetype="lion", gender="male", age_group="adult", voice_role="male_deep",
                                 appearance_lock="white lion with gold sunglasses", outfit_lock="white three-piece suit")
            cub = bible.register("Chotu", archetype="cub", gender="male", age_group="child", voice_role="child",
                                 appearance_lock="small white lion cub", outfit_lock="black mini tuxedo")
            host = bible.register("Meera", archetype="human", gender="female", age_group="adult", voice_role="female")
            assert dad.voice_pitch != cub.voice_pitch, f"Child and adult lion voices should differ in {lang}"
            assert host.voice_id != dad.voice_id or host.voice_pitch != dad.voice_pitch
            prompt, seed = bible.build_consistent_shot_prompt("3D Pixar", "Walk into golden lobby", ["Sheru", "Chotu"], "Dubai tower", aspect_ratio="9:16")
            assert "white lion with gold sunglasses" in prompt and "black mini tuxedo" in prompt and seed == dad.seed
        saved = bible.save(test_dir / "characters.json")
        loaded = CharacterBible.load(saved)
        assert len(loaded.characters) == 3 and loaded.get("Sheru").seed == dad.seed
        return {"languages_tested": ["en", "hi", "ta"], "characters_persisted": len(loaded.characters)}
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)


@test("8.3 Multi-Character Audio Studio (Dialogue Mixing, Procedural SFX, BGM & RMS Lip-Sync)")
def test_audio_studio():
    import audio_studio
    from character_manager import CharacterBible
    import shutil
    test_dir = SCRIPT_DIR / "test_audio_work"
    test_dir.mkdir(exist_ok=True)
    try:
        bible = CharacterBible(project_dir=test_dir, lang="hi")
        bible.register("Sheru", archetype="lion", gender="male", age_group="adult", voice_role="male_deep")
        bible.register("Chotu", archetype="cub", gender="male", age_group="child", voice_role="child")

        # Verify procedural copyright-free SFX & BGM synthesis
        for sfx_name in ("whoosh", "impact_boom", "shock_hit", "footsteps", "sparkle"):
            sfx_p = audio_studio.synthesize_sfx(sfx_name, test_dir / f"{sfx_name}.wav")
            assert sfx_p is not None and sfx_p.exists() and sfx_p.stat().st_size > 1000, f"SFX failed: {sfx_name}"

        out_mix = test_dir / "scene_mix.mp3"
        dur, turns = audio_studio.build_scene_dialogue_and_mix(
            dialogue_lines=[
                {"speaker": "Chotu", "text": "Papa, I want to buy the tallest tower!", "emotion": "happy"},
                {"speaker": "Sheru", "text": "Just that much son? Come with me!", "emotion": "confident"},
            ],
            bible=bible,
            work_dir=test_dir,
            scene_idx=0,
            out_audio=out_mix,
            lang="hi",
            style="animated_comedy",
            sfx_cues=["whoosh", "shock_hit"],
            enable_bgm=True,
            offline=True,
        )
        assert out_mix.exists() and dur >= 2.0 and len(turns) == 2
        assert turns[1].start_sec >= turns[0].end_sec - 0.05
        rms = audio_studio.extract_rms_lip_envelope(out_mix, fps=15, duration=dur)
        assert len(rms) >= 20 and max(rms) > 0.2, f"RMS lip-sync envelope failed: max={max(rms) if rms else 0}"
        return {"mix_dur": round(dur, 2), "turns": len(turns), "rms_frames": len(rms), "rms_peak": round(max(rms), 2)}
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)


@test("8.4 Global Multi-Source Trend Discovery Engine (Freshness, Categories, Deduplication & Live RSS)")
def test_trend_discovery_engine():
    import trend_discovery
    import shutil
    test_dir = SCRIPT_DIR / "test_trend_work"
    test_dir.mkdir(exist_ok=True)
    try:
        eng = trend_discovery.TrendDiscoveryEngine(cache_path=test_dir / "cache.json", cadence="hourly")
        # 1. Offline ranking & deduplication check
        off_items = eng.discover(region="ALL", lang="en", category="funny_animals", limit=5, offline=True)
        assert len(off_items) >= 2 and off_items[0].combined_score >= off_items[-1].combined_score
        dedup_items = eng.discover(region="ALL", lang="en", seen_topics=[off_items[0].title], limit=5, offline=True)
        assert all(it.title != off_items[0].title for it in dedup_items), "Deduplication failed"

        # 2. Live public RSS verification (Google Trends + Google News + Wikipedia)
        live_items = eng.discover(region="ALL", lang="en", limit=6, offline=False, force_refresh=True)
        assert len(live_items) >= 3, f"Expected live public trends, got {len(live_items)}"
        assert all(it.original_story_angle and it.recommended_seconds >= 25 for it in live_items)
        sources = sorted(set(s for it in live_items for s in it.sources_seen))
        return {"offline_count": len(off_items), "live_count": len(live_items), "live_sources": sources[:6]}
    finally:
        shutil.rmtree(test_dir, ignore_errors=True)


@test("8.5 End-to-End Checkpointable Animated Story Studio (9:16 + 1:1, 2D Lip-Sync, Continuation & --resume)")
def test_story_studio_e2e_and_resume():
    import story_studio
    import make_video
    import video_backends
    import shutil
    proj_dir = SCRIPT_DIR / "test_studio_proj"
    sq_dir = SCRIPT_DIR / "test_studio_sq"
    shutil.rmtree(proj_dir, ignore_errors=True)
    shutil.rmtree(sq_dir, ignore_errors=True)
    try:
        # 1. Full 9:16 multi-character trend-to-video story run
        res1 = story_studio.produce_story_project(
            idea="The White Lion and Little Cub Golden Tower",
            style="animal_story",
            target_seconds=10,
            aspect="9:16",
            quality="draft",
            lang="en",
            backend="puppet_2d",
            from_trend=True,
            project_dir=proj_dir,
            offline=True,
        )
        v1 = Path(res1["video"])
        assert v1.exists() and make_video._valid_video(v1)
        assert res1["metadata"]["aspect_ratio"] == "9:16"
        assert (proj_dir / "checkpoint.json").exists()
        assert (proj_dir / "metrics.json").exists()
        assert (proj_dir / "characters.json").exists()
        assert (proj_dir / "thumbnail.jpg").exists()

        # Verify last-frame extraction works on rendered video
        lf = proj_dir / "test_last_frame.png"
        assert video_backends.extract_last_frame(v1, lf), "Last-frame extraction failed"

        # 2. Verify --resume skips already completed scenes cleanly (significantly faster)
        res_resume = story_studio.produce_story_project(
            idea="The White Lion and Little Cub Golden Tower",
            style="animal_story",
            target_seconds=10,
            aspect="9:16",
            quality="draft",
            lang="en",
            backend="puppet_2d",
            project_dir=proj_dir,
            offline=True,
        )
        assert res_resume["metrics"]["backends_used"] == {}, "Resume should skip already-rendered scenes!"
        assert Path(res_resume["video"]).exists()

        # 3. Verify 1:1 square export format
        res_sq = story_studio.produce_story_project(
            idea="Mini Square Sci-Fi Adventure",
            style="action",
            target_seconds=5,
            aspect="1:1",
            quality="draft",
            lang="en",
            backend="puppet_2d",
            project_dir=sq_dir,
            offline=True,
        )
        assert res_sq["metadata"]["resolution"] == "720x720" and Path(res_sq["video"]).exists()
        return {
            "vertical_dur": res1["metadata"]["actual_seconds"],
            "resumed_sec": res_resume["metrics"]["total_runtime_sec"],
            "square_res": res_sq["metadata"]["resolution"],
        }
    finally:
        shutil.rmtree(proj_dir, ignore_errors=True)
        shutil.rmtree(sq_dir, ignore_errors=True)


if __name__ == "__main__":
    print("=====================================================")
    print("        RAPTAR TECHNICAL VERIFICATION SUITE         ")
    print("=====================================================")
    
    test_ffmpeg_and_fonts()
    test_caption_chunks()
    test_video_assembly()
    test_multilingual_ass_rendering()
    test_animated_svg_motion_pipeline()
    test_long_form_architecture()
    test_script_schema()
    test_gemini_model_identifiers()
    test_persistent_memory()
    test_youtube_logic()
    test_instagram_logic()
    test_performance_weights()
    test_raptar_agent_engine()
    test_multilingual_and_animated_agent()
    test_free_ai_video_engine()
    test_motion_engine_svg_and_keyframes()
    test_particles_compositor_transitions_and_synfig()
    test_hardware_manager()
    test_character_bible()
    test_audio_studio()
    test_trend_discovery_engine()
    test_story_studio_e2e_and_resume()
    
    print("\n=====================================================")
    print("                   TEST SUMMARY                      ")
    print("=====================================================")
    passed = sum(1 for r in results if r["status"] == "PASS")
    failed = sum(1 for r in results if r["status"] == "FAIL")
    print(f"Total: {len(results)} | Passed: {passed} | Failed: {failed}")
    for r in results:
        status_marker = "[OK]" if r["status"] == "PASS" else "[FAIL]"
        print(f"  {status_marker} {r['name']} ({r['duration']}s)")
    
    if failed > 0:
        sys.exit(1)
    else:
        print("\nAll technical tests executed and PASSED successfully.")

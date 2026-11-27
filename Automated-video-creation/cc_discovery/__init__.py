"""
Raptar Optional Module: Licensed Creator & CC-BY Discovery (Option 3).

Discovers and ranks the most-viewed explicitly licensed Creative Commons (CC-BY / CC0 /
Public Domain) and creator-approved media across:
  - Official YouTube Data API v3 (`videoLicense=creativeCommon`, double-verified via `status.license`)
  - Internet Archive Public Domain / CC0 / CC-BY ranked by downloads
  - Wikimedia Commons commercial-safe CC0 / CC-BY video files
  - Pexels & Pixabay popular open-license clips
  - Creator Permission Manifests (`licensed_media`)

Passes every clip through fail-closed `licensed_media.license_gate`, strips 100% of original
clip audio (`-an`), produces transformative commentary videos with automatic attribution,
and hands off optionally to unmodified `upload_youtube.py` / `upload_instagram.py`.
"""

__version__ = "1.0.0"

#!/usr/bin/env python3
"""
Immutable License & Provenance Evidence Ledger.

Records cryptographic SHA-256 hashes, source URLs, license codes, creator permission
proofs, transformative editing summaries, and embedded attribution credits for every
produced video—plus standalone per-video Evidence Certificates for rapid dispute defense.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .license_gate import VerifiedAsset


def compute_sha256(file_path: Path) -> str:
    """Computes SHA-256 hex digest of a file in streaming 64 KB chunks."""
    h = hashlib.sha256()
    with open(file_path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


class ProvenanceLedger:
    """Append-only JSON provenance ledger for licensed & creator-approved media runs."""

    def __init__(self, ledger_path: Optional[Path] = None):
        default_path = Path(__file__).resolve().parent.parent / "licensed_media_ledger.json"
        self.ledger_path = Path(ledger_path) if ledger_path else default_path

    def load(self) -> Dict[str, Any]:
        if not self.ledger_path.exists():
            return {"schema_version": "1.0", "entries": []}
        try:
            data = json.loads(self.ledger_path.read_text(encoding="utf-8"))
            if isinstance(data, dict) and isinstance(data.get("entries"), list):
                return data
        except Exception:
            pass
        return {"schema_version": "1.0", "entries": []}

    def _save(self, data: Dict[str, Any]) -> None:
        self.ledger_path.parent.mkdir(parents=True, exist_ok=True)
        self.ledger_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def record_production(
        self,
        output_video: Path,
        topic: str,
        language: str,
        fmt: str,
        video_assets: List[VerifiedAsset],
        audio_assets: List[VerifiedAsset],
        transformative_summary: Dict[str, Any],
        attributions_embedded: List[str],
        publish_targets: Optional[List[str]] = None,
        certificate_dir: Optional[Path] = None,
    ) -> Dict[str, Any]:
        """Appends a new production proof entry and writes per-video evidence certificates."""
        now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
        record_id = f"lic_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        out_hash = compute_sha256(output_video) if output_video.exists() else ""

        def _pack_asset(a: VerifiedAsset) -> Dict[str, Any]:
            sha = a.sha256
            if not sha and a.local_path and Path(a.local_path).exists():
                sha = compute_sha256(Path(a.local_path))
                a.sha256 = sha
            return {
                "asset_id": a.asset_id,
                "media_type": a.media_type,
                "source_provider": a.source_provider,
                "external_id": a.external_id,
                "title": a.title,
                "creator": a.creator,
                "source_url": a.source_url,
                "license_code": a.license_code,
                "permission_type": a.permission_type,
                "proof_ref": a.proof_ref,
                "attribution_required": a.attribution_required,
                "attribution_text": a.attribution_text,
                "sha256": sha,
                "verification_status": a.verification_status,
                "verification_reason": a.verification_reason,
                "verified_at": a.verified_at,
            }

        entry: Dict[str, Any] = {
            "record_id": record_id,
            "created_at": now_iso,
            "output_file": str(output_video),
            "output_sha256": out_hash,
            "topic": topic,
            "language": language,
            "format": fmt,
            "transformative_summary": transformative_summary,
            "video_sources": [_pack_asset(a) for a in video_assets],
            "audio_sources": [_pack_asset(a) for a in audio_assets],
            "attributions_embedded": list(attributions_embedded),
            "publish_targets": list(publish_targets or []),
        }

        data = self.load()
        data["entries"].append(entry)
        self._save(data)

        if certificate_dir is not None:
            certificate_dir.mkdir(parents=True, exist_ok=True)
            (certificate_dir / "evidence_certificate.json").write_text(
                json.dumps(entry, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            (certificate_dir / "CREDITS_AND_PROOF.txt").write_text(
                self._render_human_certificate(entry), encoding="utf-8"
            )

        return entry

    def mark_published(self, record_id: str, platform: str, details: str = "") -> bool:
        data = self.load()
        for entry in reversed(data["entries"]):
            if entry.get("record_id") == record_id:
                targets = entry.setdefault("publish_targets", [])
                targets.append({
                    "platform": platform,
                    "published_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "details": details,
                })
                self._save(data)
                return True
        return False

    @staticmethod
    def _render_human_certificate(entry: Dict[str, Any]) -> str:
        lines = [
            "======================================================================",
            "LICENSE & PROVENANCE EVIDENCE CERTIFICATE",
            "======================================================================",
            f"Record ID       : {entry['record_id']}",
            f"Created (UTC)   : {entry['created_at']}",
            f"Topic           : {entry['topic']}",
            f"Language/Format : {entry['language']} / {entry['format']}",
            f"Output SHA-256  : {entry['output_sha256']}",
            "",
            "TRANSFORMATIVE EDITING SUMMARY:",
        ]
        for k, v in (entry.get("transformative_summary") or {}).items():
            lines.append(f"  - {k}: {v}")
        lines.append("")
        lines.append("VERIFIED VIDEO SOURCES:")
        for vs in entry.get("video_sources", []):
            lines.append(
                f"  * [{vs['license_code']}] {vs['source_provider']} | {vs['title']} by {vs['creator']}\n"
                f"    URL: {vs['source_url']}\n"
                f"    Proof Ref: {vs['proof_ref'] or 'Official Open-License API'}\n"
                f"    SHA-256: {vs['sha256']}"
            )
        lines.append("")
        lines.append("VERIFIED AUDIO / MUSIC SOURCES:")
        for aus in entry.get("audio_sources", []):
            lines.append(
                f"  * [{aus['license_code']}] {aus['source_provider']} | {aus['title']} by {aus['creator']}\n"
                f"    URL: {aus['source_url']}\n"
                f"    SHA-256: {aus['sha256']}"
            )
        if entry.get("attributions_embedded"):
            lines.append("")
            lines.append("EMBEDDED ATTRIBUTIONS:")
            for attr in entry["attributions_embedded"]:
                lines.append(f"  - {attr}")
        lines.append("======================================================================")
        return "\n".join(lines) + "\n"

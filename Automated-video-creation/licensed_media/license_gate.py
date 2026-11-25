#!/usr/bin/env python3
"""
Fail-Closed License & Permission Verification Gate.

Enforces strict commercial-reuse and derivative-work compliance BEFORE any media
is downloaded, processed, or published:
- Approves only explicit allowlisted open licenses (Pexels, Pixabay, CC0, Public Domain,
  CC-BY) and documented creator permissions (self_owned, written_creator_license, verified_cc_by).
- Hard-rejects NonCommercial (NC), NoDerivatives (ND), unknown/empty licenses,
  expired permissions, missing proof references, and unverified third-party
  YouTube/Instagram scraping URLs.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse


ALLOWED_OPEN_LICENSES: Dict[str, Dict[str, Any]] = {
    "PEXELS": {"commercial": True, "derivatives": True, "attribution_required": False},
    "PIXABAY": {"commercial": True, "derivatives": True, "attribution_required": False},
    "CC0": {"commercial": True, "derivatives": True, "attribution_required": False},
    "CC0-1.0": {"commercial": True, "derivatives": True, "attribution_required": False},
    "PUBLIC-DOMAIN": {"commercial": True, "derivatives": True, "attribution_required": False},
    "PDM-1.0": {"commercial": True, "derivatives": True, "attribution_required": False},
    "CC-BY": {"commercial": True, "derivatives": True, "attribution_required": True},
    "CC-BY-2.0": {"commercial": True, "derivatives": True, "attribution_required": True},
    "CC-BY-3.0": {"commercial": True, "derivatives": True, "attribution_required": True},
    "CC-BY-4.0": {"commercial": True, "derivatives": True, "attribution_required": True},
    "CC-BY-SA-3.0": {"commercial": True, "derivatives": True, "attribution_required": True},
    "CC-BY-SA-4.0": {"commercial": True, "derivatives": True, "attribution_required": True},
}

ALLOWED_CREATOR_PERMISSIONS = {
    "SELF-OWNED",
    "WRITTEN-CREATOR-LICENSE",
    "VERIFIED-CC-BY",
}

BLOCKED_RESTRICTIONS = (
    "NC",
    "ND",
    "NONCOMMERCIAL",
    "NON-COMMERCIAL",
    "NODERIV",
    "NO-DERIV",
    "ALL-RIGHTS-RESERVED",
    "ALL RIGHTS RESERVED",
    "COPYRIGHTED",
    "FAIR-USE",
    "FAIR USE",
    "EDITORIAL-ONLY",
    "EDITORIAL ONLY",
)

UNSCRAPABLE_HOST_FRAGMENTS = (
    "youtube.com",
    "youtu.be",
    "instagram.com",
    "instagr.am",
    "tiktok.com",
)


@dataclass
class LicenseDecision:
    approved: bool
    normalized_license: str
    reason: str
    attribution_required: bool = False
    attribution_line: str = ""
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class VerifiedAsset:
    asset_id: str
    media_type: str               # "video" | "audio"
    source_provider: str          # "pexels" | "pixabay" | "wikimedia" | "archive" | "openverse" | "freesound" | "manifest_youtube" | "manifest_instagram" | "own_instagram_api" | "manifest_local"
    external_id: str
    title: str
    creator: str
    source_url: str
    download_url: str = ""
    local_path: str = ""
    license_code: str = ""
    permission_type: str = ""     # "self_owned" | "written_creator_license" | "verified_cc_by" | ""
    proof_ref: str = ""
    allow_commercial: bool = True
    allow_derivatives: bool = True
    expires_at: str = ""
    attribution_required: bool = False
    attribution_text: str = ""
    duration_sec: float = 0.0
    width: int = 0
    height: int = 0
    sha256: str = ""
    verification_status: str = "pending"   # "approved" | "rejected" | "pending"
    verification_reason: str = ""
    verified_at: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def normalize_license_code(raw: str) -> str:
    """Normalizes varied API license strings into canonical tokens."""
    s = re.sub(r"\s+", " ", str(raw or "").strip()).upper()
    if not s:
        return ""
    if "PUBLIC DOMAIN" in s or s in ("PD", "PDM", "PDM 1.0", "PUBLICDOMAIN", "USGOV", "PD-US", "PD-OLD"):
        return "PUBLIC-DOMAIN"
    if "CC0" in s or "ZERO" in s or "NO COPYRIGHT" in s:
        return "CC0-1.0"
    if "PEXELS" in s:
        return "PEXELS"
    if "PIXABAY" in s:
        return "PIXABAY"
    if s in ("SELF_OWNED", "SELF-OWNED", "OWNED", "OWN_ACCOUNT"):
        return "SELF-OWNED"
    if s in ("WRITTEN_CREATOR_LICENSE", "WRITTEN-CREATOR-LICENSE", "CREATOR_APPROVED", "CREATOR-APPROVED"):
        return "WRITTEN-CREATOR-LICENSE"
    if s in ("VERIFIED_CC_BY", "VERIFIED-CC-BY"):
        return "VERIFIED-CC-BY"
    # Detect Creative Commons variants cleanly
    compact = re.sub(r"[^A-Z0-9.]+", "-", s).strip("-")
    if compact.startswith("CC-BY") or "CREATIVE-COMMONS-ATTRIBUTION" in compact:
        # Preserve NC / ND tokens so the blocker catches them!
        if "NC" in compact.split("-") or "NONCOMMERCIAL" in compact:
            return compact
        if "ND" in compact.split("-") or "NODERIV" in compact:
            return compact
        ver = re.search(r"(\d+\.\d+)", compact)
        suffix = f"-{ver.group(1)}" if ver else "-4.0"
        if "SA" in compact.split("-"):
            return f"CC-BY-SA{suffix}"
        return f"CC-BY{suffix}"
    return compact


def _contains_blocked_restriction(raw: str) -> Optional[str]:
    up = str(raw or "").upper()
    tokens = set(re.split(r"[^A-Z0-9]+", up))
    for blk in BLOCKED_RESTRICTIONS:
        if blk in ("NC", "ND"):
            if blk in tokens:
                return blk
        elif blk in up:
            return blk
    return None


def _is_unscrapable_page_url(url: str) -> bool:
    if not url:
        return False
    try:
        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return False
    return any(host == frag or host.endswith("." + frag) for frag in UNSCRAPABLE_HOST_FRAGMENTS)


def _is_expired(expires_at: str) -> bool:
    if not str(expires_at or "").strip():
        return False
    try:
        dt = datetime.fromisoformat(expires_at.strip().replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt <= datetime.now(timezone.utc)
    except Exception:
        # Unparseable expiration date -> fail closed!
        return True


def build_attribution_line(asset: VerifiedAsset, norm_license: str) -> str:
    if asset.attribution_text.strip():
        return asset.attribution_text.strip()
    creator = asset.creator.strip() or "Original Creator"
    title = asset.title.strip() or asset.external_id or "Media Clip"
    src = asset.source_url.strip()
    if src:
        return f'"{title}" by {creator} ({norm_license}) — {src}'
    return f'"{title}" by {creator} ({norm_license})'


def verify_asset_license(asset: VerifiedAsset) -> LicenseDecision:
    """
    Fail-closed verification gate. Updates asset.verification_status,
    asset.verification_reason, asset.attribution_required, and asset.verified_at.
    """
    now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds")
    warnings: List[str] = []

    def _reject(reason: str, norm: str = "") -> LicenseDecision:
        asset.verification_status = "rejected"
        asset.verification_reason = reason
        asset.verified_at = now_iso
        return LicenseDecision(approved=False, normalized_license=norm, reason=reason, warnings=warnings)

    # 1. Explicit commercial/derivative permission flags must be true
    if not asset.allow_commercial:
        return _reject("Commercial reuse is explicitly disallowed (allow_commercial=False).")
    if not asset.allow_derivatives:
        return _reject("Derivative editing is explicitly disallowed (allow_derivatives=False).")

    # 2. Check expiration (if provided)
    if _is_expired(asset.expires_at):
        return _reject(f"Permission/license is expired or has an invalid expires_at date: '{asset.expires_at}'.")

    # 3. Block raw scraping of third-party YouTube/Instagram watch/reel pages
    if asset.download_url and _is_unscrapable_page_url(asset.download_url):
        return _reject(
            "Direct downloading from YouTube/Instagram web URLs is blocked to preserve platform ToS compliance. "
            "Supply a local export, authorized direct media file URL, or own Instagram Graph API media ID."
        )

    # 4. Block restricted license terms (NC, ND, All Rights Reserved, Fair Use)
    for field_val in (asset.license_code, asset.permission_type):
        bad = _contains_blocked_restriction(field_val)
        if bad:
            return _reject(f"Blocked license restriction detected ({bad}) in '{field_val}'.", norm=normalize_license_code(field_val))

    # 5. Creator / Own-Account Permission Path (YouTube/Instagram/Local manifest or Own IG API)
    is_creator_source = asset.source_provider.startswith("manifest_") or asset.source_provider == "own_instagram_api"
    norm_perm = normalize_license_code(asset.permission_type)
    norm_lic = normalize_license_code(asset.license_code)

    if is_creator_source:
        effective = norm_perm or norm_lic
        if effective not in ALLOWED_CREATOR_PERMISSIONS and effective not in ALLOWED_OPEN_LICENSES:
            return _reject(
                f"Creator/platform asset requires permission_type in {sorted(ALLOWED_CREATOR_PERMISSIONS)} "
                f"or an allowlisted open license; got '{asset.permission_type or asset.license_code}'."
            )
        if not asset.proof_ref.strip():
            return _reject(
                "Creator/platform asset is missing required 'proof_ref' (written permission email/doc ID, "
                "YouTube channel ownership ID, or own Instagram account ID)."
            )
        if not (asset.local_path.strip() or asset.download_url.strip()):
            return _reject("Asset has neither an authorized local_path nor an authorized direct media download_url.")

        attr_req = effective in ("WRITTEN-CREATOR-LICENSE", "VERIFIED-CC-BY") or bool(
            ALLOWED_OPEN_LICENSES.get(effective, {}).get("attribution_required")
        )
        if attr_req and not (asset.creator.strip() or asset.attribution_text.strip()):
            return _reject(f"Attribution is required for '{effective}', but creator/attribution_text is missing.")

        attr_line = build_attribution_line(asset, effective) if attr_req else ""
        asset.license_code = effective
        asset.attribution_required = attr_req
        if attr_line:
            asset.attribution_text = attr_line
        asset.verification_status = "approved"
        asset.verification_reason = f"Approved via documented creator permission ({effective} | proof={asset.proof_ref})."
        asset.verified_at = now_iso
        return LicenseDecision(
            approved=True,
            normalized_license=effective,
            reason=asset.verification_reason,
            attribution_required=attr_req,
            attribution_line=attr_line,
            warnings=warnings,
        )

    # 6. Official Open-License API Path (Pexels, Pixabay, Wikimedia, Internet Archive, Openverse, Freesound)
    if norm_lic not in ALLOWED_OPEN_LICENSES:
        return _reject(
            f"Open-source asset license '{asset.license_code}' (normalized: '{norm_lic}') is not on the commercial-safe allowlist.",
            norm=norm_lic,
        )

    rule = ALLOWED_OPEN_LICENSES[norm_lic]
    attr_req = bool(rule["attribution_required"])
    if attr_req and not (asset.creator.strip() or asset.attribution_text.strip()):
        warnings.append("Creator metadata was sparse; fallback provider attribution generated.")

    attr_line = build_attribution_line(asset, norm_lic) if attr_req else ""
    asset.license_code = norm_lic
    asset.attribution_required = attr_req
    if attr_line:
        asset.attribution_text = attr_line
    asset.verification_status = "approved"
    asset.verification_reason = f"Approved via verified open license ({norm_lic} from {asset.source_provider})."
    asset.verified_at = now_iso
    return LicenseDecision(
        approved=True,
        normalized_license=norm_lic,
        reason=asset.verification_reason,
        attribution_required=attr_req,
        attribution_line=attr_line,
        warnings=warnings,
    )


def format_attribution_block(assets: List[VerifiedAsset], compact: bool = False) -> str:
    """Formats clean attribution credits for YouTube descriptions (full) or Instagram captions (compact)."""
    lines: List[str] = []
    seen = set()
    for a in assets:
        if a.verification_status != "approved":
            continue
        if a.attribution_required or a.attribution_text.strip():
            txt = a.attribution_text.strip() or build_attribution_line(a, a.license_code)
            if txt.lower() not in seen:
                seen.add(txt.lower())
                lines.append(txt)
    if not lines:
        return ""
    if compact:
        short = " | ".join(lines[:3])
        return f"Credits: {short}"[:350]
    return "Media & Music Credits (Licensed / Permitted):\n" + "\n".join(f"- {ln}" for ln in lines)

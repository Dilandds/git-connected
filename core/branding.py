"""
Centralised branding / marketing URLs for ECTOFORM.

==============================================================
SWITCHING THE PUBLIC WEBSITE DOMAIN
==============================================================
All public-facing URLs (pricing page, support page, etc.) are
derived from MARKETING_SITE_URL below. The current production
domain is https://ectoform.studio. To point the desktop app at
a different domain, change MARKETING_SITE_URL in ONE place here.
Nothing else in the Python codebase needs to be touched.

The PyInstaller .spec files do NOT bake these URLs into the
binary — they read from this module at runtime — so a rebuild
is enough.

If you want to override without editing code (e.g. in CI), set:
    ECTOFORM_MARKETING_SITE_URL=https://your-new-domain.com
    ECTOFORM_BUY_URL=...        # optional, full override
    ECTOFORM_SUPPORT_URL=...    # optional, full override

Anything else hard-coded to "web-palette-probe.lovable.app"
elsewhere is a bug — keep the single source of truth here.
==============================================================
"""

from __future__ import annotations

import os

# ---- Single source of truth for the public website ----
MARKETING_SITE_URL = os.environ.get(
    "ECTOFORM_MARKETING_SITE_URL",
    "https://ectoform.studio",
).rstrip("/")

# ---- Derived URLs (override individually via env if needed) ----
BUY_URL = os.environ.get(
    "ECTOFORM_BUY_URL",
    f"{MARKETING_SITE_URL}/pricing",
).strip()

SUPPORT_URL = os.environ.get(
    "ECTOFORM_SUPPORT_URL",
    f"{MARKETING_SITE_URL}/activate-help",
).strip()

# Subscription management portal (Lemon Squeezy customer portal, etc.).
# No marketing-site default — leave empty unless explicitly set.
MANAGE_URL = os.environ.get("ECTOFORM_MANAGE_URL", "").strip()

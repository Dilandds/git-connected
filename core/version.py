"""
Single source of truth for the ECTOFORM application version.

Bump this string, commit, then tag the commit `v<version>` and push the tag
to trigger the GitHub Actions release workflow.

    git tag v1.0.1
    git push origin v1.0.1

Follow semver: MAJOR.MINOR.PATCH. Never re-tag a published version.
"""

__version__ = "1.0.4"

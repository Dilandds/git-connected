## Update default marketing URL

In `core/branding.py`, change the fallback default of `MARKETING_SITE_URL` from `https://web-palette-probe.lovable.app` to `https://ectoform.studio`.

Keep the `os.environ.get("ECTOFORM_MARKETING_SITE_URL", ...)` wrapper so the env override still works. `BUY_URL` and `SUPPORT_URL` derive from it automatically, so no other edits needed.

### Diff

```python
MARKETING_SITE_URL = os.environ.get(
    "ECTOFORM_MARKETING_SITE_URL",
    "https://ectoform.studio",
).rstrip("/")
```

Also update the comment block referencing the old Lovable preview domain to mention `ectoform.studio` as the current production domain.

No other files reference `web-palette-probe.lovable.app` (verified earlier).
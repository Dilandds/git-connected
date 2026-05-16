# Phase 1 — Steps 1–3: Tag → Build → GitHub Release

Goal: pushing a git tag like `v1.0.1` triggers GitHub Actions to build **all six installers** (Commercial + Education × Windows + macOS-13 + macOS-14) and publish them as a single GitHub Release with a `version.json` manifest. No in-app updater code and no R2 yet — this step only proves the release pipeline works end-to-end and you can see/download the assets in the GitHub Releases UI.

## Editions & platforms (6 installers per release)

| Edition | Windows | macOS Intel (macos-13) | macOS Apple Silicon (macos-14) |
|---|---|---|---|
| Commercial | `ECTOFORM-Setup-<v>.exe` | `ECTOFORM-<v>-macOS-x64.dmg` | `ECTOFORM-<v>-macOS-arm64.dmg` |
| Education  | `ECTOFORM-Education-Setup-<v>.exe` | `ECTOFORM-Education-<v>-macOS-x64.dmg` | `ECTOFORM-Education-<v>-macOS-arm64.dmg` |

Education is **not dropped** — first-class release artifact, parity with Commercial.

Why both Mac runners: `macos-13` produces an Intel (x86_64) DMG, `macos-14` produces an Apple Silicon (arm64) DMG. PyInstaller doesn't cross-compile or produce universal binaries by default — each runner builds for its own CPU. Shipping both means Intel Mac users get a native build (no Rosetta) and M-series users get a native arm64 build.

## What gets added to the desktop repo

### 1. `core/version.py` (new — single source of truth)
```python
__version__ = "1.0.1"
```
Spec files and build scripts read from this. No more hard-coded `"1.0.0"` scattered across 4 spec files and 4 build scripts.

### 2. Spec + build script changes
- All 4 `.spec` files: replace literal `'1.0.0'` in `CFBundleShortVersionString` / `CFBundleVersion` with a read from `core/version.py`.
- `build_mac.sh`, `build_mac_education.sh`, `build_windows.ps1`, `build_windows_education.ps1`: read version from `core/version.py` and emit versioned, arch-suffixed output filenames. Arch suffix (`-x64` / `-arm64`) is detected from `uname -m` so the same script works on both Mac runners.

### 3. `.github/workflows/release.yml` (new — leaves existing `build.yml` untouched)
Trigger: tag push matching `v*.*.*`. Existing `build.yml` (manual `workflow_dispatch`, with mac matrix) stays as the dev sanity-check workflow.

Jobs:
- **build-windows** (`windows-latest`) — builds Commercial EXE, then Education EXE. Uploads both as workflow artifacts.
- **build-macos** (matrix: `macos-13`, `macos-14`) — each runner builds Commercial `.app`+`.dmg`, then Education `.app`+`.dmg`. Uploads 2 DMGs per runner with arch-tagged artifact names.
- **publish-release** (needs both) — downloads the 6 installer artifacts, computes SHA-256 for each, generates `version.json` + `SHA256SUMS.txt`, then uses `softprops/action-gh-release@v2` to create the GitHub Release with all 8 files attached.

Permissions: `contents: write`. Uses built-in `GITHUB_TOKEN` — no secrets to configure.

### `version.json` shape (Phase 1)
```json
{
  "version": "1.0.1",
  "released_at": "2026-05-16T12:00:00Z",
  "notes_url": "https://github.com/<owner>/<repo>/releases/tag/v1.0.1",
  "commercial": {
    "windows":      { "url": "...ECTOFORM-Setup-1.0.1.exe",          "sha256": "<hex>", "size": 0 },
    "macos_x64":    { "url": "...ECTOFORM-1.0.1-macOS-x64.dmg",      "sha256": "<hex>", "size": 0 },
    "macos_arm64":  { "url": "...ECTOFORM-1.0.1-macOS-arm64.dmg",    "sha256": "<hex>", "size": 0 }
  },
  "education": {
    "windows":      { "url": "...ECTOFORM-Education-Setup-1.0.1.exe",        "sha256": "<hex>", "size": 0 },
    "macos_x64":    { "url": "...ECTOFORM-Education-1.0.1-macOS-x64.dmg",    "sha256": "<hex>", "size": 0 },
    "macos_arm64":  { "url": "...ECTOFORM-Education-1.0.1-macOS-arm64.dmg",  "sha256": "<hex>", "size": 0 }
  }
}
```
Splitting `commercial` vs `education` and `macos_x64` vs `macos_arm64` lets the in-app updater (Phase 1 Step 5) pick the right installer using `ECTOFORM_EDITION` + `platform.machine()`.

### Release assets (8 files)
1. `ECTOFORM-Setup-1.0.1.exe`
2. `ECTOFORM-1.0.1-macOS-x64.dmg`
3. `ECTOFORM-1.0.1-macOS-arm64.dmg`
4. `ECTOFORM-Education-Setup-1.0.1.exe`
5. `ECTOFORM-Education-1.0.1-macOS-x64.dmg`
6. `ECTOFORM-Education-1.0.1-macOS-arm64.dmg`
7. `version.json`
8. `SHA256SUMS.txt`

## How to verify it works

1. Bump `core/version.py` to `1.0.1`, commit, then:
   ```
   git tag v1.0.1
   git push origin v1.0.1
   ```
2. Open the Actions tab — `build-windows` runs once and `build-macos` runs twice (one per matrix entry); total ~15–20 min.
3. Open the Releases page — `v1.0.1` should show all 8 assets attached.
4. Download one EXE, one Intel DMG, one arm64 DMG; install on real hardware; confirm both editions launch.
5. `curl -L https://github.com/<owner>/<repo>/releases/latest/download/version.json` returns the JSON above. This is the URL the updater will hit in Step 5.

## Open question

I need the **desktop repo's `<owner>/<repo>` slug** to hard-code into the `version.json` asset URLs (e.g. `your-org/ectoform-desktop`). What's the GitHub path?

## Out of scope for this step
- `core/updater.py` (in-app update prompt) — Step 5
- R2 mirror upload — Phase 2
- Code signing (Windows EV cert / Apple Developer ID) — separate decision
- Website `/download` page changes — none, per your earlier message

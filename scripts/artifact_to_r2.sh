#!/usr/bin/env bash
# Download a file from a URL and upload it to the R2 bucket used by
# release.yml, so it can be re-shared as a fast CDN link instead of a slow
# GitHub Artifacts / Actions download.
#
# Handles two kinds of source URL:
#   1. A plain public URL (GitHub Release asset, an existing R2/CDN link,
#      or any other directly-downloadable link) — fetched anonymously.
#   2. A GitHub Actions artifact page URL
#      (https://github.com/<owner>/<repo>/actions/runs/<run_id>/artifacts/<artifact_id>)
#      — these are NEVER truly public, even on a public repo; GitHub requires
#      an authenticated request. This script shells out to `gh` for those,
#      so `gh auth login` must already be done.
#
# Usage:
#   scripts/artifact_to_r2.sh <url> [r2-key]
#
#   <url>     Source URL (see above).
#   [r2-key]  Destination path inside the bucket. Defaults to
#             "manual-uploads/<filename>".
#
# Required env vars (same secrets release.yml uses in CI):
#   R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_ACCOUNT_ID
# Optional:
#   R2_BUCKET   Bucket name (default: ectoform-downloads)
#
# Requires: curl, aws CLI, and — only for Actions artifact URLs — gh CLI.

set -euo pipefail

URL="${1:?Usage: $0 <url> [r2-key]}"
R2_BUCKET="${R2_BUCKET:-ectoform-downloads}"

: "${R2_ACCESS_KEY_ID:?Set R2_ACCESS_KEY_ID (Cloudflare R2 access key)}"
: "${R2_SECRET_ACCESS_KEY:?Set R2_SECRET_ACCESS_KEY (Cloudflare R2 secret key)}"
: "${R2_ACCOUNT_ID:?Set R2_ACCOUNT_ID (Cloudflare account id)}"

command -v aws >/dev/null || { echo "Error: aws CLI is required (pip install awscli or brew install awscli)"; exit 1; }
command -v curl >/dev/null || { echo "Error: curl is required"; exit 1; }

WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT

FILE_TO_UPLOAD=""

if [[ "$URL" =~ github\.com/([^/]+)/([^/]+)/actions/runs/([0-9]+)/artifacts/([0-9]+) ]]; then
  OWNER="${BASH_REMATCH[1]}"
  REPO="${BASH_REMATCH[2]}"
  RUN_ID="${BASH_REMATCH[3]}"
  ARTIFACT_ID="${BASH_REMATCH[4]}"

  echo "Detected a GitHub Actions artifact URL (owner=$OWNER repo=$REPO run=$RUN_ID artifact=$ARTIFACT_ID)."
  echo "This requires an authenticated request — using gh CLI."
  command -v gh >/dev/null || { echo "Error: gh CLI is required for Actions artifact URLs. https://cli.github.com"; exit 1; }

  ARTIFACT_NAME="$(gh api "repos/$OWNER/$REPO/actions/artifacts/$ARTIFACT_ID" --jq .name)"
  echo "Resolved artifact name: $ARTIFACT_NAME"

  EXTRACT_DIR="$WORKDIR/extracted"
  gh run download "$RUN_ID" -R "$OWNER/$REPO" -n "$ARTIFACT_NAME" -D "$EXTRACT_DIR"

  # gh unzips the artifact automatically. If it contained exactly one file
  # (true for our DMG/ZIP artifacts, which are stored uncompressed — see
  # build.yml's compression-level: 0), upload that file as-is. Otherwise
  # (e.g. a raw .app bundle artifact, which is a whole directory tree),
  # zip it back up first so there's one file to upload.
  mapfile -t FILES < <(find "$EXTRACT_DIR" -type f)
  if [[ ${#FILES[@]} -eq 1 ]]; then
    FILE_TO_UPLOAD="${FILES[0]}"
  else
    command -v zip >/dev/null || { echo "Error: zip is required to bundle a multi-file artifact"; exit 1; }
    ZIP_PATH="$WORKDIR/$ARTIFACT_NAME.zip"
    (cd "$EXTRACT_DIR" && zip -qr "$ZIP_PATH" .)
    FILE_TO_UPLOAD="$ZIP_PATH"
  fi
else
  echo "Treating as a plain public URL."
  FILENAME="$(basename "${URL%%\?*}")"
  FILE_TO_UPLOAD="$WORKDIR/$FILENAME"
  curl -fL --progress-bar -o "$FILE_TO_UPLOAD" "$URL"
fi

SIZE="$(du -h "$FILE_TO_UPLOAD" | cut -f1)"
echo "Downloaded: $FILE_TO_UPLOAD ($SIZE)"

R2_KEY="${2:-manual-uploads/$(basename "$FILE_TO_UPLOAD")}"

echo "Uploading to r2://$R2_BUCKET/$R2_KEY ..."
AWS_ACCESS_KEY_ID="$R2_ACCESS_KEY_ID" \
AWS_SECRET_ACCESS_KEY="$R2_SECRET_ACCESS_KEY" \
aws s3 cp "$FILE_TO_UPLOAD" "s3://$R2_BUCKET/$R2_KEY" \
  --endpoint-url "https://$R2_ACCOUNT_ID.r2.cloudflarestorage.com" \
  --region auto

echo ""
echo "Done."
echo "  s3 path:    s3://$R2_BUCKET/$R2_KEY"
echo "  Public URL: https://downloads.ectoform.studio/$R2_KEY"
echo "  (public only if the R2_KEY prefix is served by the bucket's custom domain — check the Cloudflare R2 dashboard if unsure)"

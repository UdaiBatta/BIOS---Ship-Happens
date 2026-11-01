#!/usr/bin/env bash
# One-command local setup and launch of MOTIONIQ (backend + worker + viewer).
# Usage, from the repository root:   bash scripts/run_local.sh
# Everything stays on this machine: the server binds to 127.0.0.1 only.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$PWD"
CLIP="data/private/mytronlabs-000060-016.mp4"
RELEASE="ps4-baseline-handoff-20261031"
REPO="UdaiBatta/BIOS---Ship-Happens"

if [ -z "${MOTIONIQ_FFMPEG_DIR:-}" ] && [ -n "${EGOHAND_FFMPEG_DIR:-}" ]; then export MOTIONIQ_FFMPEG_DIR="$EGOHAND_FFMPEG_DIR"; fi
if [ -n "${MOTIONIQ_FFMPEG_DIR:-}" ]; then export PATH="$MOTIONIQ_FFMPEG_DIR:$PATH"; fi

need() { command -v "$1" >/dev/null 2>&1 || { echo "Missing: $1. $2"; exit 1; }; }
need uv "Install: https://docs.astral.sh/uv/ (macOS: brew install uv)"
need ffmpeg "Install FFmpeg (macOS: brew install ffmpeg; Debian/Ubuntu: sudo apt-get install ffmpeg)"
need ffprobe "Install FFmpeg (it provides ffprobe)"

echo "==> Installing dependencies"
uv sync --extra dev --extra viewer --extra backend --extra hybrid
uv run motioniq fetch-model >/dev/null
uv run rerun analytics disable >/dev/null 2>&1 || true
uv run motioniq fetch-model --rtm >/dev/null 2>&1 || echo "    (optional RTM hand models not downloaded; the experimental hybrid preset stays hidden)"
uv run motioniq doctor | grep -E '"mediapipe_runtime"' || true

if [ ! -f "$CLIP" ] && ! find media -type f \( -iname "*.mp4" -o -iname "*.mov" -o -iname "*.mkv" -o -iname "*.avi" -o -iname "*.m4v" -o -iname "*.webm" \) 2>/dev/null | grep -q .; then
  echo "==> $CLIP not found; downloading it from the private release (needs: gh auth login)"
  need gh "Install GitHub CLI (macOS: brew install gh) and run: gh auth login"
  TMP="$(mktemp -d)"
  gh release download "$RELEASE" --repo "$REPO" --dir "$TMP" -p ps4-source-video.zip -p SHA256SUMS
  (cd "$TMP" && grep ps4-source-video.zip SHA256SUMS | (shasum -a 256 -c - 2>/dev/null || sha256sum -c -))
  uv run python -m zipfile -e "$TMP/ps4-source-video.zip" .
  rm -rf "${TMP:?}"
fi

# A server or worker left over from an earlier launch keeps running OLD code; stop it first.
OLD=$(pgrep -f "manage.py (runserver 127.0.0.1:8000|motioniq_worker)" || true)
if [ -n "$OLD" ]; then
  echo "==> Stopping MOTIONIQ server/worker process(es) from an earlier launch: $OLD"
  kill $OLD 2>/dev/null || true
  sleep 2
fi

echo "==> Preparing the backend database"
cd backend
uv run python manage.py migrate -v0
TO_REGISTER=()
[ -f "$ROOT/$CLIP" ] && TO_REGISTER+=("$ROOT/$CLIP")
[ -d "$ROOT/media" ] && TO_REGISTER+=("$ROOT/media")
uv run python manage.py motioniq_register "${TO_REGISTER[@]}"

echo "==> Starting worker and server (Ctrl+C stops both)"
uv run python manage.py motioniq_worker --recover &
WORKER=$!
trap 'kill $WORKER 2>/dev/null || true' EXIT INT TERM
echo "    Open http://127.0.0.1:8000/  -> Backend row: pick the video, preset recall, start 0, length 30, Process"
uv run python manage.py runserver 127.0.0.1:8000 --noreload

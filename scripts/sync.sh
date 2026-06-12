#!/usr/bin/env bash
# One command: commit code -> GitHub, and (via post-commit hook) artifacts -> Drive.
# Usage:  bash scripts/sync.sh "commit message"
set -euo pipefail
cd "$(git rev-parse --show-toplevel)"

msg="${1:-wip}"
git add -A
if git diff --cached --quiet; then
  echo "[sync] nothing to commit"
else
  git commit -m "$msg"      # post-commit hook fires scripts/push_drive.sh in the background
fi
git push
echo "[sync] pushed to GitHub. Drive sync runs in background (see .git/drive_push.log)."

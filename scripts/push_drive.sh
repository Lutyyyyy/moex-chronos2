#!/usr/bin/env bash
# Push OUTPUTS/ARTIFACTS ONLY to the partner's shared Google Drive folder.
# Destination: moex-hack/ilia   (moex-hack is owned by mich.bnce@gmail.com; you have Editor)
# Code is NOT sent here — code lives on GitHub. This handles results/models/data only.
#
# Runs automatically from .git/hooks/post-commit, or manually:  bash scripts/push_drive.sh
set -euo pipefail

MOEX_HACK_ID="16TiMTbWsEdefGG9Igse460LA0XT_m4-g"   # partner's shared "moex-hack" folder
REMOTE="gdrive"                                     # rclone remote name (created via `rclone config`)
DEST="${REMOTE}:ilia"                               # -> moex-hack/ilia (your isolated subfolder)

cd "$(git rev-parse --show-toplevel)"

# Degrade gracefully if rclone isn't set up yet — never block a commit.
if ! command -v rclone >/dev/null 2>&1; then
  echo "[push_drive] rclone not installed — skipping Drive sync"; exit 0
fi
if ! rclone listremotes 2>/dev/null | grep -q "^${REMOTE}:"; then
  echo "[push_drive] rclone remote '${REMOTE}' not configured yet — run: rclone config"; exit 0
fi

echo "[push_drive] syncing artifacts -> moex-hack/ilia ..."
rclone copy . "$DEST" \
  --drive-root-folder-id "$MOEX_HACK_ID" \
  --include "runs/**" \
  --include "ag_chronos2_ft/**" \
  --include "*.parquet" \
  --include "*.csv" \
  --include "*.bin" \
  --include "*.pt" \
  --include "*.ckpt" \
  --include "*.npz" \
  --include "*.safetensors" \
  --include "*_run.ipynb" \
  --transfers 4 --checkers 8 \
  --log-level NOTICE
echo "[push_drive] done."

#!/usr/bin/env bash
set -euo pipefail

TARGET_DIR="${HOME}/plugins/wrkflw"
REPO_URL="${1:-https://github.com/iamanandkris/wrkflw.git}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
CODEX_HOME_DIR="${CODEX_HOME:-${HOME}/.codex}"
SKILL_TARGET="${CODEX_HOME_DIR}/skills/wrkflw-discuss"

mkdir -p "$(dirname "${TARGET_DIR}")"

if [ "${1:-}" = "--local" ] || [ "${1:-}" = "local" ]; then
  echo "Installing local wrkflw plugin from ${SOURCE_DIR} into ${TARGET_DIR}"
  mkdir -p "${TARGET_DIR}"
  rsync -a --delete \
    --exclude ".git" \
    --exclude ".workflow" \
    --exclude "__pycache__" \
    --exclude ".pytest_cache" \
    "${SOURCE_DIR}/" "${TARGET_DIR}/"
elif [ -d "${TARGET_DIR}/.git" ]; then
  echo "Updating existing wrkflw plugin in ${TARGET_DIR}"
  git -C "${TARGET_DIR}" pull --ff-only
else
  echo "Cloning wrkflw plugin into ${TARGET_DIR}"
  git clone "${REPO_URL}" "${TARGET_DIR}"
fi

rm -rf "${TARGET_DIR}/.workflow"

mkdir -p "${SKILL_TARGET}"
cp "${TARGET_DIR}/skills/wrkflw-discuss/SKILL.md" "${SKILL_TARGET}/SKILL.md"

cat <<EOF

wrkflw is available at:
  ${TARGET_DIR}

Active Codex skill updated at:
  ${SKILL_TARGET}/SKILL.md

Next:
1. Point your Codex plugin marketplace/config at that path if needed.
2. Reload Codex/VS Code if plugin or skill discovery is cached.
EOF

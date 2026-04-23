#!/usr/bin/env bash
set -euo pipefail

TARGET_DIR="${HOME}/plugins/wrkflw"
REPO_URL="${1:-https://github.com/iamanandkris/wrkflw.git}"

mkdir -p "$(dirname "${TARGET_DIR}")"

if [ -d "${TARGET_DIR}/.git" ]; then
  echo "Updating existing wrkflw plugin in ${TARGET_DIR}"
  git -C "${TARGET_DIR}" pull --ff-only
else
  echo "Cloning wrkflw plugin into ${TARGET_DIR}"
  git clone "${REPO_URL}" "${TARGET_DIR}"
fi

cat <<EOF

wrkflw is available at:
  ${TARGET_DIR}

Next:
1. Point your Codex plugin marketplace/config at that path if needed.
2. Reload Codex/VS Code if plugin discovery is cached.
EOF

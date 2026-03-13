#!/usr/bin/env bash
# Edict for OpenCode installer (macOS / Linux)
# Usage:  curl -fsSL https://raw.githubusercontent.com/CyberPunk-2022/edict-opencode/main/install.sh | bash
#   or:   bash install.sh            (from local clone)
set -euo pipefail

INSTALL_DIR="${HOME}/.config/opencode/edict-opencode"
PLUGINS_DIR="${HOME}/.config/opencode/plugins"
SKILLS_DIR="${HOME}/.config/opencode/skills"
REPO_URL="https://github.com/CyberPunk-2022/edict-opencode.git"

echo "Installing edict-opencode for OpenCode..."

# If run from a local clone (install.sh exists in cwd), use that as source
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [ -f "${SCRIPT_DIR}/agent_config.json" ]; then
  # Local install: copy/link from current directory
  SOURCE_DIR="${SCRIPT_DIR}"
  if [ "${SOURCE_DIR}" != "${INSTALL_DIR}" ]; then
    mkdir -p "$(dirname "${INSTALL_DIR}")"
    if [ -d "${INSTALL_DIR}" ] && [ ! -L "${INSTALL_DIR}" ]; then
      rm -rf "${INSTALL_DIR}"
    fi
    ln -sfn "${SOURCE_DIR}" "${INSTALL_DIR}"
    echo "  → Linked ${INSTALL_DIR} → ${SOURCE_DIR}"
  fi
else
  # Remote install: clone or update
  if [ -d "${INSTALL_DIR}/.git" ]; then
    echo "  → Updating existing installation..."
    git -C "${INSTALL_DIR}" pull --ff-only
  else
    echo "  → Cloning repository..."
    git clone "${REPO_URL}" "${INSTALL_DIR}"
  fi
  SOURCE_DIR="${INSTALL_DIR}"
fi

# Create directories
mkdir -p "${PLUGINS_DIR}" "${SKILLS_DIR}"

# Remove stale symlinks / old copies
rm -f  "${PLUGINS_DIR}/edict.js"
rm -rf "${SKILLS_DIR}/edict"

# Create symlinks
ln -s "${SOURCE_DIR}/.opencode/plugins/edict.js" "${PLUGINS_DIR}/edict.js"
ln -s "${SOURCE_DIR}/skills"                      "${SKILLS_DIR}/edict"

echo ""
echo "Done! edict-opencode installed."
echo ""
echo "  Plugin : ${PLUGINS_DIR}/edict.js"
echo "  Skills : ${SKILLS_DIR}/edict"
echo ""
echo "Restart OpenCode to activate."
echo ""
echo "Quick start in any project:"
echo "  python ${SOURCE_DIR}/scripts/edict_tasks_init.py --path . --demo"

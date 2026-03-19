#!/usr/bin/env bash
# deploy.sh — Canonical runtime deploy command for Big Pi.
# Copies a committed gddp-runtime snapshot into ~/opclaw/scripts and writes
# a deploy marker showing exactly which git commit is running there.
#
# Usage:
#   bash deploy/deploy.sh
#   bash deploy/deploy.sh --restart-intake

set -euo pipefail

usage() {
    cat <<'EOF'
Usage:
  bash deploy/deploy.sh
  bash deploy/deploy.sh --restart-intake

Options:
  --restart-intake   Restart opclaw-intake.service after syncing scripts
EOF
}

RESTART_INTAKE=0

while (($# > 0)); do
    case "$1" in
        --restart-intake)
            RESTART_INTAKE=1
            shift
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown argument: $1" >&2
            usage >&2
            exit 1
            ;;
    esac
done

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OPCLAW_DIR="${OPCLAW_ROOT:-$HOME/opclaw}"
TARGET_SCRIPTS_DIR="$OPCLAW_DIR/scripts"
MARKER_PATH="$OPCLAW_DIR/.gddp-runtime-deploy.json"
PREVIOUS_SCRIPTS_DIR="$OPCLAW_DIR/scripts.previous"

mkdir -p "$OPCLAW_DIR"/{db,events/{raw,normalized},jobs}
mkdir -p "$OPCLAW_DIR"

COMMIT_SHA="$(git -C "$REPO_ROOT" rev-parse HEAD)"
COMMIT_SHORT="$(git -C "$REPO_ROOT" rev-parse --short HEAD)"
BRANCH_NAME="$(git -C "$REPO_ROOT" rev-parse --abbrev-ref HEAD)"
DEPLOYED_AT="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

TMP_SCRIPTS_DIR="$(mktemp -d "$OPCLAW_DIR/scripts.deploy.XXXXXX")"
cp -R "$REPO_ROOT/scripts/." "$TMP_SCRIPTS_DIR/"

rm -rf "$PREVIOUS_SCRIPTS_DIR"
if [ -d "$TARGET_SCRIPTS_DIR" ]; then
    mv "$TARGET_SCRIPTS_DIR" "$PREVIOUS_SCRIPTS_DIR"
fi
mv "$TMP_SCRIPTS_DIR" "$TARGET_SCRIPTS_DIR"
rm -rf "$PREVIOUS_SCRIPTS_DIR"

cat > "$MARKER_PATH" <<EOF
{
  "source_repo": "$REPO_ROOT",
  "source_branch": "$BRANCH_NAME",
  "source_commit": "$COMMIT_SHA",
  "source_commit_short": "$COMMIT_SHORT",
  "deployed_at_utc": "$DEPLOYED_AT",
  "deployed_scripts_dir": "$TARGET_SCRIPTS_DIR"
}
EOF

echo "=== GDAD Runtime Deploy ==="
echo "  commit:  $COMMIT_SHORT ($COMMIT_SHA)"
echo "  scripts: $TARGET_SCRIPTS_DIR"
echo "  marker:  $MARKER_PATH"

if (( RESTART_INTAKE )); then
    if command -v systemctl >/dev/null 2>&1; then
        sudo systemctl restart opclaw-intake
        echo "  intake:  restarted"
    else
        echo "  intake:  systemctl unavailable, restart skipped"
    fi
fi

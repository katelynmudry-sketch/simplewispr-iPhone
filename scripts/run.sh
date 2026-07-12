#!/usr/bin/env bash
set -euo pipefail

# Resolve project root from this script's location so the script works
# from the dev tree (~/Documents/…/MyWispr/) and from the production
# install path (~/Library/Application Support/MyWispr/app/).
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
PROJECT_DIR=$(dirname "$SCRIPT_DIR")

VENV="$PROJECT_DIR/.venv"
if [ ! -d "$VENV" ]; then
    echo "ERROR: venv not found at $VENV — run scripts/setup.sh first" >&2
    exit 1
fi

# shellcheck source=/dev/null
source "$VENV/bin/activate"

if [[ "${1:-}" == "--cleanup-only" ]]; then
    # Synchronous exec for launchd: launchd waits for python to exit and
    # captures the exit code.
    exec python "$PROJECT_DIR/src/main.py" "$@"
else
    # exec python so the LaunchServices-tracked PID chains all the way to the
    # NSApplication (rumps), satisfying RunningBoard's check-in requirement.
    # TCC attribution to MyWispr.app is preserved through the responsible-process
    # chain: LaunchServices launched the trampoline, which exec'd bash, which
    # exec'd python — all under the same tracked PID.
    # NOTE: validate Mic prompt attribution after any change to this exec chain.
    exec python "$PROJECT_DIR/src/main.py" "$@"
fi

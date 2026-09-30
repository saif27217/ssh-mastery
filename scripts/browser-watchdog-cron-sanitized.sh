#!/bin/bash
# browser-watchdog-cron.sh — 6-hourly cron: ensure browser daemon, report failures only.
# Empty stdout = silent (no notification). Non-empty stdout = delivered as message.
# Exit 0 always (so cron doesn't alarm on expected downtime).

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BROWSER_SCRIPT="$SCRIPT_DIR/browser-ensure-sanitized.sh"

# Run recovery (not just check)
OUTPUT=$(bash "$BROWSER_SCRIPT" 2>&1)
EXIT_CODE=$?

if [[ $EXIT_CODE -ne 0 ]]; then
    echo "⚠️ Browser Server Watchdog"
    echo "$OUTPUT"
    echo ""
    echo "Manual recovery: bash $BROWSER_SCRIPT"
fi
# If exit 0, stdout is empty → silent delivery (nothing sent)
exit 0

#!/bin/bash
# tunnel-watchdog-cron.sh — Hourly cron: ensure tunnels, report failures only.
# Empty stdout = silent (no notification). Non-empty stdout = delivered as message.
# Exit 0 always (so cron doesn't alarm on expected downtime).

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TUNNEL_SCRIPT="$SCRIPT_DIR/tunnel-ensure.sh"

# Run recovery (not just check)
OUTPUT=$("$TUNNEL_SCRIPT" 2>&1)
EXIT_CODE=$?

if [[ $EXIT_CODE -ne 0 ]]; then
    echo "⚠️ SSH Tunnel Watchdog"
    echo "$OUTPUT"
    echo ""
    echo "Manual recovery: bash $TUNNEL_SCRIPT"
fi
# If exit 0, stdout is empty → silent delivery (nothing sent)
exit 0

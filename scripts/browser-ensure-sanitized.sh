#!/bin/bash
# browser-ensure.sh — Idempotent guardian for termux-browser-pilot daemon.
#
# Checks if the browser daemon is running on Termux; starts it if not.
#
# Usage:
#   ./browser-ensure.sh            # ensure running, exit 0 if ok
#   ./browser-ensure.sh --check    # check only, no recovery
#   ./browser-ensure.sh --json     # JSON output (for cron/monitoring)
#
# Exit codes:
#   0 — daemon healthy (or recovered)
#   1 — daemon unrecoverable
#   2 — --check mode, daemon down

set -uo pipefail

# ─── Termux connection ───────────────────────────────────────────────
TERMUX_HOST="<remote-ip>"
TERMUX_SSH_PORT="<ssh-port>"
TERMUX_USER="<user>"
SSH_KEY="$HOME/.ssh/id_ed25519"
TBP_DIR="/data/data/com.termux/files/home/termux-browser-pilot"

SSH_OPTS=(
    -o StrictHostKeyChecking=no
    -o ConnectTimeout=10
    -o BatchMode=yes
)

CHECK_ONLY=false
JSON_OUTPUT=false
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

for arg in "$@"; do
    case "$arg" in
        --check) CHECK_ONLY=true ;;
        --json) JSON_OUTPUT=true ;;
    esac
done

# ─── Helpers ──────────────────────────────────────────────────────────
ssh_termux() {
    ssh "${SSH_OPTS[@]}" -i "$SSH_KEY" "$TERMUX_USER@$TERMUX_HOST" -p "$TERMUX_SSH_PORT" "$1" 2>/dev/null
}

daemon_running() {
    local output
    output=$(ssh_termux "cd $TBP_DIR && python3 cli.py status" 2>/dev/null)
    echo "$output" | grep -q "PID:" && return 0
    return 1
}

get_daemon_info() {
    ssh_termux "cd $TBP_DIR && python3 cli.py status" 2>/dev/null
}

start_daemon() {
    # Kill any stale process first
    ssh_termux "pkill -f 'cli.py' 2>/dev/null; sleep 1"
    # Start fresh — use setsid to fully detach from SSH session
    ssh_termux "cd $TBP_DIR && setsid nohup python3 cli.py start --browser firefox > /tmp/tbp-start.log 2>&1 < /dev/null &"
    sleep 5
}

# ─── Main ─────────────────────────────────────────────────────────────
STATUS="healthy"
DETAILS=""

if ! daemon_running; then
    STATUS="down"
    DETAILS="daemon not running"

    if $CHECK_ONLY; then
        if $JSON_OUTPUT; then
            echo "{\"status\":\"error\",\"timestamp\":\"$TIMESTAMP\",\"service\":\"termux-browser-pilot\",\"details\":\"$DETAILS\"}"
        else
            echo "termux-browser-pilot: DOWN — $DETAILS"
        fi
        exit 2
    fi

    echo "[browser-pilot] Daemon down — attempting restart..."
    start_daemon

    # Verify recovery
    if daemon_running; then
        STATUS="recovered"
        DETAILS="daemon restarted successfully"
        echo "[browser-pilot] Recovered successfully."
    else
        STATUS="failed"
        DETAILS="restart failed — check Termux device"
        echo "[browser-pilot] Recovery failed."
        if $JSON_OUTPUT; then
            echo "{\"status\":\"error\",\"timestamp\":\"$TIMESTAMP\",\"service\":\"termux-browser-pilot\",\"details\":\"$DETAILS\"}"
        else
            echo "termux-browser-pilot: FAILED — $DETAILS"
        fi
        exit 1
    fi
else
    INFO=$(get_daemon_info)
    PID=$(echo "$INFO" | grep "PID:" | awk '{print $2}')
    UPTIME=$(echo "$INFO" | grep "Uptime:" | awk '{print $2}' | cut -d's' -f1)
    echo "[browser-pilot] Healthy (PID $PID, uptime ${UPTIME}s)"
fi

if $JSON_OUTPUT; then
    echo "{\"status\":\"ok\",\"timestamp\":\"$TIMESTAMP\",\"service\":\"termux-browser-pilot\",\"pid\":$(echo "$INFO" | grep "PID:" | awk '{print $2}'),\"uptime\":$(echo "$INFO" | grep "Uptime:" | awk '{print $2}' | cut -d's' -f1)}"
fi

exit 0

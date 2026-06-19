#!/bin/bash
# tunnel-ensure.sh — Idempotent SSH tunnel guardian for multiple tunnels.
#
# Edit the TUNNELS array below for your environment.
# Format: LOCAL_PORT|REMOTE_HOST|SSH_PORT|SSH_USER|SSH_KEY_PATH|REMOTE_TARGET|LABEL
#
# Usage:
#   ./tunnel-ensure.sh            # ensure all tunnels, exit 0 if ok
#   ./tunnel-ensure.sh --check    # check only, no recovery
#   ./tunnel-ensure.sh --json     # JSON output (for cron/monitoring)
#
# Exit codes:
#   0 — all tunnels healthy (or recovered)
#   1 — one or more tunnels unrecoverable
#   2 — --check mode, at least one tunnel down

set -euo pipefail

# ─── Tunnel definitions ───────────────────────────────────────────────
TUNNELS=(
    "12028|<ammara-ip>|22|<user>|<ssh-key-path>|localhost:20128|9router"
    "12029|<termux-ip>|8022|<user>|<ssh-key-path>|localhost:20128|termux"
)

# ─── Common SSH options ──────────────────────────────────────────────
SSH_OPTS=(
    -o StrictHostKeyChecking=no
    -o ServerAliveInterval=15
    -o ServerAliveCountMax=3
    -o TCPKeepAlive=yes
    -o ExitOnForwardFailure=yes
    -o ConnectTimeout=10
    -o BatchMode=yes
)

# ─── Helpers ──────────────────────────────────────────────────────────
CHECK_ONLY=false
JSON_OUTPUT=false
TIMESTAMP=$(date '+%Y-%m-%d %H:%M:%S')

for arg in "$@"; do
    case "$arg" in
        --check) CHECK_ONLY=true ;;
        --json) JSON_OUTPUT=true ;;
    esac
done

port_listening() {
    ss -tlnp 2>/dev/null | grep -q ":${1} " && return 0 || return 1
}

http_healthy() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 \
        --max-time 10 "http://127.0.0.1:${1}/v1/models" 2>/dev/null)
    [[ "$code" != "000" && "$code" != "" ]]
}

ssh_reachable() {
    local host=$1 port=$2 user=$3 key=$4
    ssh -o ConnectTimeout=8 -o StrictHostKeyChecking=no -o BatchMode=yes \
        -i "$key" "$user@$host" -p "$port" 'echo 1' </dev/null 2>/dev/null
}

kill_tunnel_on_port() {
    local port=$1
    local pid
    pid=$(ss -tlnp 2>/dev/null | grep ":${port} " | grep -oP 'pid=\K[0-9]+' | head -1)
    if [[ -n "$pid" ]]; then
        kill "$pid" 2>/dev/null || true
        sleep 1
        kill -9 "$pid" 2>/dev/null || true
        sleep 0.5
    fi
    pkill -f "ssh.*-L.*127.0.0.1:${port}:" 2>/dev/null || true
    sleep 0.5
}

start_tunnel() {
    local port=$1 host=$2 ssh_port=$3 user=$4 key=$5 target=$6
    nohup ssh "${SSH_OPTS[@]}" -i "$key" -N \
        -L "127.0.0.1:${port}:${target}" \
        "$user@$host" -p "$ssh_port" \
        > /dev/null 2>&1 &
    sleep 2
}

# ─── Main ─────────────────────────────────────────────────────────────
FAIL_COUNT=0
RESULTS=()

for def in "${TUNNELS[@]}"; do
    IFS='|' read -r LPORT RHOST RSPORT RUSER RKEY RTARGET LABEL <<< "$def"
    STATUS="healthy"
    ACTION="none"

    if ! port_listening "$LPORT"; then
        STATUS="down"
        ACTION="port_not_listening"
    else
        if ! http_healthy "$LPORT"; then
            STATUS="stale"
            ACTION="http_failed"
        fi
    fi

    if [[ "$STATUS" != "healthy" ]]; then
        if $CHECK_ONLY; then
            FAIL_COUNT=$((FAIL_COUNT + 1))
            RESULTS+=("$LABEL: $STATUS ($ACTION)")
            continue
        fi

        echo "[$LABEL] Tunnel $STATUS — attempting recovery..."
        kill_tunnel_on_port "$LPORT"

        if ! ssh_reachable "$RHOST" "$RSPORT" "$RUSER" "$RKEY"; then
            echo "[$LABEL] SSH unreachable ($RHOST:$RSPORT)."
            FAIL_COUNT=$((FAIL_COUNT + 1))
            RESULTS+=("$LABEL: ssh_unreachable")
            continue
        fi

        start_tunnel "$LPORT" "$RHOST" "$RSPORT" "$RUSER" "$RKEY" "$RTARGET"

        if port_listening "$LPORT" && http_healthy "$LPORT"; then
            echo "[$LABEL] Recovered."
            ACTION="recovered"
        else
            echo "[$LABEL] Recovery failed."
            FAIL_COUNT=$((FAIL_COUNT + 1))
            RESULTS+=("$LABEL: recovery_failed")
            continue
        fi
    else
        echo "[$LABEL] Healthy (port $LPORT)"
    fi
done

if $JSON_OUTPUT; then
    if [[ $FAIL_COUNT -eq 0 ]]; then
        echo '{"status":"ok","timestamp":"'"$TIMESTAMP"'","tunnels":[]}'
    else
        printf '{"status":"error","timestamp":"%s","tunnels":[' "$TIMESTAMP"
        first=true
        for r in "${RESULTS[@]}"; do
            $first || printf ','
            first=false
            printf '"%s"' "$r"
        done
        echo ']}'
    fi
fi

if $CHECK_ONLY && [[ $FAIL_COUNT -gt 0 ]]; then
    exit 2
elif [[ $FAIL_COUNT -gt 0 ]]; then
    exit 1
else
    exit 0
fi

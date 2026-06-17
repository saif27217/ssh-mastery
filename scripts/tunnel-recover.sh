#!/bin/bash
# tunnel-recover.sh — Verify and restart SSH tunnel to Termux endpoint
# Usage: ./tunnel-recover.sh <LOCAL_PORT> <REMOTE_PORT> <REMOTE_IP> <SSH_PORT> <USER> [SSH_KEY]
#
# Exit codes:
#   0 — tunnel healthy or successfully re-established
#   2 — SSH unreachable (device asleep / sshd not running)
#   3 — tunnel failed to start (remote service likely down)

LOCAL_PORT="${1:-12029}"
REMOTE_PORT="${2:-20128}"
REMOTE_IP="${3:-100.70.18.84}"
SSH_PORT="${4:-8022}"
USER="${5:-u0_a221}"
KEY="${6:-$HOME/.ssh/id_ed25519}"

echo "=== Tunnel Recovery: $(date) ==="

# 1. Check if tunnel already running and healthy
if ss -tlnp | grep -q "$LOCAL_PORT"; then
    PID=$(ss -tlnp | grep "$LOCAL_PORT" | grep -oP 'pid=\K[0-9]+')
    echo "Active tunnel on $LOCAL_PORT (PID $PID). Testing..."
    RESULT=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 5 http://127.0.0.1:$LOCAL_PORT/v1/models 2>&1)
    if [ "$RESULT" != "000" ]; then
        echo "Tunnel healthy — HTTP $RESULT"
        exit 0
    fi
    echo "Tunnel stale — killing PID $PID"
    kill "$PID" 2>/dev/null
    sleep 1
fi

# 2. Test SSH reachability
echo "Testing SSH to $USER@$REMOTE_IP:$SSH_PORT..."
if ! ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=no -o BatchMode=yes -i "$KEY" "$USER@$REMOTE_IP" -p "$SSH_PORT" 'echo connected' 2>/dev/null; then
    echo "FAIL: SSH unreachable. Cannot establish tunnel."
    echo "Action needed: Wake device / restart sshd"
    exit 2
fi

# 3. Start tunnel
echo "Starting tunnel: $LOCAL_PORT → $REMOTE_IP:$REMOTE_PORT..."
nohup ssh -o StrictHostKeyChecking=no -o ConnectTimeout=10 \
    -o ServerAliveInterval=15 -o ServerAliveCountMax=3 \
    -o TCPKeepAlive=yes -o ExitOnForwardFailure=yes \
    -o BatchMode=yes \
    -i "$KEY" -N -L "127.0.0.1:$LOCAL_PORT:localhost:$REMOTE_PORT" \
    "$USER@$REMOTE_IP" -p "$SSH_PORT" \
    > /dev/null 2>&1 &

sleep 2

# 4. Verify
if ss -tlnp | grep -q "$LOCAL_PORT"; then
    echo "Tunnel established on $LOCAL_PORT"
    curl -s -o /dev/null -w "Service HTTP %{http_code}\n" --connect-timeout 5 http://127.0.0.1:$LOCAL_PORT/v1/models
    exit 0
else
    echo "FAIL: Tunnel did not start. Check remote service."
    exit 3
fi

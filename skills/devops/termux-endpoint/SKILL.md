---
name: termux-endpoint
description: Use when configuring or troubleshooting an Android Termux device as an SSH terminal backend or a persistent server endpoint for Hermes.
version: 1.0.0
author: Sak & Hermes
license: MIT
metadata:
  hermes:
    tags: [termux, ssh, tailscale, android, reverse-tunnel, endpoint, devops]
    related_skills: [ssh-remote-backend, 9router-setup]
---

# Termux SSH & Server Endpoint

## Overview
This skill outlines how to configure, secure, and manage an Android Termux environment as a remote terminal backend or service endpoint for a local Hermes agent. Since Android environments have unique security, sandboxing, power-management, and dynamic linker traits, running persistent automation requires specific configurations distinct from a standard VPS or Docker container.

## When to Use
- When configuring an Android Termux device (connected via Tailscale) as the terminal backend for Hermes.
- When deploying persistent services (like a FastAPI 1minAI proxy, 9router, or LLM server) directly inside Termux.
- When troubleshooting SSH handshakes, key rejection, network drops, or background process terminations on mobile devices.
- **Do not use for**: Standard Linux VPS or Docker host configurations that do not run on Android/Termux.

---

## Technical Specifications & Configuration

### 1. Connection Parameters (Default Android Sandbox)
- **Default Port**: `8022` (Termux does not bind to system port `22` by default).
- **Default Username**: Android sandbox user (e.g., `u0_a221` or similar, determined by running `whoami` in Termux).
- **Authentication**: Key-based only. Password-based authentication should be disabled in production.

### 2. Device Power & Persistence Policy (Wake Lock)
Android aggressively optimizes battery usage by sleeping CPU cores and killing background tasks. To keep the Tailscale daemon and SSH server alive when the screen is off:
1. **Disable Battery Optimization**: Exclude both the **Tailscale** and **Termux** applications from system battery optimization settings on the Android device.
2. **Acquire Termux Wake Lock**: Run the following command inside Termux to prevent CPU sleep:
   ```bash
   termux-wake-lock
   ```
   *Verify state*: A persistent notification from Termux saying "Wake lock held" should be visible in the Android status bar.

---

## Implementation Steps

### Step 1: Install SSH Server on Termux
On the Android device, open Termux and run:
```bash
pkg update && pkg upgrade -y
pkg install openssh -y
sshd
```
*Verify port listing*:
```bash
ss -tlnp | grep 8022
```

### Step 2: Establish SSH Key Authentication
1. **Generate Keys on VPS (Hermes Host)**:
   ```bash
   ssh-keygen -t ed25519 -N "" -f ~/.ssh/id_ed25519
   ```
2. **Add to Termux `authorized_keys`**:
   Copy the contents of `~/.ssh/id_ed25519.pub` from the VPS and write it to `~/.ssh/authorized_keys` on Termux.
3. **Configure Permissions on Termux**:
   ```bash
   chmod 700 ~/.ssh
   chmod 600 ~/.ssh/authorized_keys
   ```
4. **Key Verification Rule**:
   Always verify the fingerprint or output public key matches between the hosts to avoid the `Offering public key... rejected` handshake failure:
   - *VPS side*: `ssh-keygen -y -f ~/.ssh/id_ed25519`
   - *Termux side*: `cat ~/.ssh/authorized_keys`

### Step 3: Reverse SSH Tunnel Pattern (Behind NAT)
If the Termux device is behind a strict NAT or direct Tailscale port access is blocked, establish a reverse tunnel from Termux to the VPS:
1. **Run from Termux**:
   ```bash
   # Forwards port 8022 on the VPS (localhost:8022) to local Termux SSH port 8022
   ssh -R 8022:localhost:8022 -N -f <user>@<VPS_IP>
   ```
2. **Configure VPS Hermes Terminal Backend (`~/.hermes/.env`)**:
   ```bash
   export TERMINAL_BACKEND=ssh
   export TERMINAL_SSH_HOST=localhost
   export TERMINAL_SSH_PORT=8022
   export TERMINAL_SSH_USER=u0_a221
   export TERMINAL_SSH_KEY=/home/sak/.ssh/id_ed25519
   ```

---

## Server Deployment: Native vs Proot-Distro

When deploying API servers (e.g., FastAPI, 9router proxies) inside Termux, choose the environment carefully:

| Environment | Purpose | Persistence | Pitfalls |
|-------------|---------|-------------|----------|
| **Native Termux** | Persistent background servers, long-running APIs, cron hooks. | **Yes**. Background processes survive SSH session exit. | Native packages like `pydantic-core` or cryptography must be compiled unless pre-built `pkg` versions are used. |
| **Proot-Distro (Ubuntu)** | Interactive debugging, testing libraries, quick python tools. | **No**. Processes are killed immediately upon session disconnect. | `proot-distro login` enforces `--kill-on-exit` behavior. Dynamic linkers may throw `invalid ELF header` outside the wrapper. |

### Persistent Native Deployment Recipe (FastAPI / 1minAI Proxy)
1. **Install python & system dependencies natively**:
   ```bash
   pkg install python python-pip -y
   ```
2. **Set up virtual environment**:
   ```bash
   python3 -m venv ~/venv
   source ~/venv/bin/activate
   pip install uvicorn fastapi pydantic aiohttp httpx tiktoken python-dotenv
   ```
3. **Handle Compilation Failures**:
   If a pip package fails compiling on aarch64, install it via native packages:
   ```bash
   pkg install python-pydantic python-cryptography -y
   ```
4. **Start Background Process (Survives Exit)**:
   Use `nohup` combined with native execution (never inside proot):
   ```bash
   nohup ~/venv/bin/python3 ~/oneminai_server.py > ~/server.log 2>&1 &
   ```
5. **Verify Process Survival**:
   Disconnect the SSH session, reconnect, and run:
   ```bash
   ps aux | grep python
   ```

---

## Mandatory Pre-Flight: Reachability & Health Verification Protocol

Before assuming the Termux endpoint is usable (and especially before retrying a failed call), run **this exact sequence** to pinpoint the failure. Do not skip steps and do not retry without diagnosing the failure point first.

### Consolidated Health Check (One-Shot)

This single command tests **all 4 layers** and reports which one failed:

```bash
echo "=== HEALTH CHECK: $(date) ===" && \
echo "" && \
echo "---[1/4 TAILSCALE REACHABILITY]---" && \
if tailscale ping --c 1 --until-direct=false <remote-ip> 2>&1 | grep -q "pong"; then echo "PASS: tailscale ping"; else echo "FAIL: tailscale unreachable"; fi && \
echo "" && \
echo "---[2/4 SSH CONNECTIVITY]---" && \
ssh -o ConnectTimeout=8 -o StrictHostKeyChecking=no -o BatchMode=yes -i ~/.ssh/id_ed25519 -p <ssh-port> <user>@<remote-ip> 'echo PASS: ssh_connected' 2>&1 || echo "FAIL: ssh_unreachable" && \
echo "" && \
echo "---[3/4 REMOTE SERVICE HEALTH]---" && \
ssh -o ConnectTimeout=5 -o StrictHostKeyChecking=no -o BatchMode=yes -i ~/.ssh/id_ed25519 -p <ssh-port> <user>@<remote-ip> 'curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:<REMOTE_PORT>/health 2>/dev/null || curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:<REMOTE_PORT>/v1/models 2>/dev/null || echo "SERVICE_DOWN"' 2>&1 && \
echo "" && \
echo "---[4/4 TUNNEL LOCAL PORT]---" && \
if ss -tlnp | grep -q "<LOCAL_PORT>"; then echo "PASS: tunnel_listening on <LOCAL_PORT>"; else echo "FAIL: no_tunnel_on_<LOCAL_PORT>"; fi && \
echo "" && \
echo "=== END HEALTH CHECK ==="
```

**Rule**: If any layer fails, diagnose and fix that layer before proceeding. Do not retry the tunnel or service call until the failing layer reports PASS.

### Per-Layer Diagnosis & Recovery

| Layer | Test Command | Failure Signal | Recovery Action |
|-------|-------------|----------------|-----------------|
| **1. Tailscale** | `tailscale ping --c 1 --until-direct=false <remote-ip>` | No pong, "no route to host" | 1. Ask user to bring screen on / unlock device (battery sleep) 2. Check Android battery optimization is off for Tailscale + Termux 3. Ensure Wi-Fi/mobile data is on 4. Have user run `tailscale up` in Termux |
| **2. SSH** | `timeout 8 bash -c 'echo >/dev/tcp/<remote-ip>/<ssh-port>' && echo OPEN \|\| echo CLOSED` | `CLOSED` or `Connection refused` | 1. SSH daemon may have died from Android OOM: have user open Termux, run `sshd` 2. Wake lock may have expired: run `termux-wake-lock` 3. Key auth mismatch: verify `authorized_keys` on device |
| **3. Remote Service** | `ssh ... <user>@<remote-ip> 'curl -s http://127.0.0.1:<REMOTE_PORT>/health'` | `Connection refused`, empty response | 1. Service process crashed — restart remotely: `cd ~/app && nohup ... &` 2. Service bound to wrong interface (0.0.0.0 vs 127.0.0.1) 3. Port conflict — check with `ss -tlnp \| grep <REMOTE_PORT>` on device |
| **4. Tunnel** | `ss -tlnp \| grep <LOCAL_PORT>` | No listening socket | 1. SSH tunnel process died — restart tunnel 2. If `ExitOnForwardFailure=yes` + remote port down, SSH exits silently — fix remote service first 3. **Never retry tunnel without confirming remote service is healthy first** |

### Critical Rule: The Retry Trap

**Do not retry blindly.** Every retry without diagnosis is wasted time. The sequence from the consolidated check tells you exactly where to look:
- `FAIL: tailscale_unreachable` → fix device connectivity, stop trying SSH
- `FAIL: ssh_unreachable` → fix SSH daemon, stop trying to curl the remote service
- `FAIL: service_down` → fix the app on device, stop trying to tunnel
- `FAIL: no_tunnel` → fix the tunnel, then verify the service is reachable through it

### Why the 9router Tunnel Specifically Failed

The failure we diagnosed was at **Layer 4 (Tunnel)** with symptom `Timeout, server not responding` — but the root cause was actually **Layer 1 (Tailscale)** or **Layer 2 (SSH)** intermittently dropping when the Android device went to sleep. The tunnel SSH process cannot recover from a Tailscale drop without `ServerAliveInterval` + `ServerAliveCountMax` + `TCPKeepAlive` and systemd `Restart=always`.

## Tunnel Recovery Script

Save as `~/.hermes/scripts/tunnel-recover.sh` for automated one-shot recovery:

```bash
#!/bin/bash
# tunnel-recover.sh — Verify and restart SSH tunnel to Termux endpoint
# Usage: ./tunnel-recover.sh <LOCAL_PORT> <REMOTE_PORT> <REMOTE_IP> <SSH_PORT> <USER> [SSH_KEY]

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
```

## Common Pitfalls

1. **The Proot Session Termination Trap**
   *Problem*: Launching a server inside `proot-distro` using `nohup &` or `setsid` fails to persist after closing the SSH shell.
   *Fix*: Always deploy background services in the **native Termux** environment. Keep proot strictly for interactive testing.

2. **Android Sleep Mode & Tailscale Disconnect**
   *Problem*: SSH commands time out when the device screen is off.
   *Fix*: Verify `termux-wake-lock` is running and battery optimization is disabled for both applications.

3. **Blind Retry Accumulation**
   *Problem*: User asks "retry" 6+ times without diagnosing, wasting time.
   *Fix*: Run the Consolidated Health Check first. Stop retrying Layer 4 when Layer 1 or 2 is down — no tunnel survives a dead Tailscale link.

4. **Tailscale MTU Blackhole**
   *Problem*: HTTP request headers return instantly, but transfer stalls indefinitely with `exit code 18`.
   *Fix*: Enable TCP MTU Probing on the VPS and Termux host:
   ```bash
   echo 1 | sudo tee /proc/sys/net/ipv4/tcp_mtu_probing
   ```

5. **Permissions and SELinux Blocks**
   *Problem*: Key-based login fails with `Permission denied (publickey)`.
   *Fix*: Ensure correct directory ownership, permissions (700/600), and double-check Termux SELinux policies if accessing files outside the app's private directories.

6. **Tunnel SSH Dies on Network Blip**
   *Problem*: Tailscale drops briefly, tunnel SSH exits, and nobody restarts it.
   *Fix*: Use systemd `Restart=always` (see AGENTS.md) or run the `tunnel-recover.sh` script as a cron job.

---

## Verification Checklist

- [ ] **Wake Lock Active**: Termux wake lock held (persistent Android notification present).
- [ ] **Layer 1 — Tailscale Reachability**: `tailscale ping <remote-ip>` returns pong.
- [ ] **Layer 2 — SSH Authentication**: `ssh ... 'echo connected'` works without password prompt.
- [ ] **Layer 3 — Remote Service Health**: `curl -s http://127.0.0.1:<REMOTE_PORT>/health` returns HTTP 200 on the device.
- [ ] **Layer 4 — Tunnel Listening**: `ss -tlnp | grep <LOCAL_PORT>` shows the tunnel process.
- [ ] **End-to-End Verification**: `curl -s http://127.0.0.1:<LOCAL_PORT>/v1/models` returns valid JSON (not connection refused).
- [ ] **Service Persistence**: Services started natively survive terminal disconnect.

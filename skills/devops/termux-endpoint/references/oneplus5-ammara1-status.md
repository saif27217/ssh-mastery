# Active Termux Endpoints (OnePlus 5 / Ammara-1)

This reference documents the diagnostic status and active configurations of the Termux endpoints.

## 1. Network Status (via Tailscale)
- **OnePlus 5**: `100.70.18.84`
  - **Status**: Online / Active (Direct connection over IPv6).
  - **User**: `u0_a221`
  - **SSH Port**: `8022`
  - **Authentication**: Key-based (`~/.ssh/id_ed25519`).
- **Ammara-1**: `100.77.100.52`
  - **Status**: Offline (Active; relay "blr"; last seen 18m ago).
  - **User**: `shark`
  - **SSH Port**: `8022`

## 2. Active Services on OnePlus 5 (`100.70.18.84`)
- **1minAI FastAPI Proxy**:
  - **Port**: `9000` (Localhost-bound).
  - **Status**: Healthy (Uvicorn native background process PID 2559).
  - **Verification**: `curl -s http://127.0.0.1:9000/health` returns HTTP 200.
- **9router**:
  - **Port**: `20128` (Localhost-bound).
  - **Status**: Online (Node process running inside a `proot-distro` container).
  - **Verification**: `curl -s http://127.0.0.1:20128/v1/models` returns the exposed model list.

## 3. SSH Tunnels on VPS (`srv1405080`)
- **9router Tunnel**:
  - **Forwarding**: `127.0.0.1:12029` (VPS) → `localhost:20128` (OnePlus 5).
  - **Status**: Active (SSH process PID variable — use `ss -tlnp | grep 12029`).
  - **Verification**: `curl -s http://127.0.0.1:12029/v1/models` successfully resolves to the phone's 9router endpoint.

## 4. Pre-Flight Health Check (Last Verified: Jun 16, 2026)
```bash
# Consolidated 4-layer check — always run before use
echo "Layer 1 (Tailscale):"  && tailscale ping --c 1 --until-direct=false 100.70.18.84 | grep -q pong && echo "PASS" || echo "FAIL"
echo "Layer 2 (SSH):"        && ssh -o ConnectTimeout=8 -o BatchMode=yes u0_a221@100.70.18.84 -p 8022 'echo PASS' 2>&1 || echo "FAIL"
echo "Layer 3 (9router):"    && ssh -o ConnectTimeout=5 -o BatchMode=yes u0_a221@100.70.18.84 -p 8022 \
  'curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:20128/v1/models' 2>&1
echo "Layer 4 (Tunnel):"     && ss -tlnp | grep -q 12029 && echo "PASS" || echo "FAIL"
```

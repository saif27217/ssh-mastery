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

## Common Pitfalls

1. **The Proot Session Termination Trap**
   *Problem*: Launching a server inside `proot-distro` using `nohup &` or `setsid` fails to persist after closing the SSH shell.
   *Fix*: Always deploy background services in the **native Termux** environment. Keep proot strictly for interactive testing.

2. **Android Sleep Mode & Tailscale Disconnect**
   *Problem*: SSH commands time out when the device screen is off.
   *Fix*: Verify `termux-wake-lock` is running and battery optimization is disabled for both applications.

3. **Tailscale MTU Blackhole**
   *Problem*: HTTP requests headers return instantly, but the transfer stalls indefinitely with `exit code 18`.
   *Fix*: Enable TCP MTU Probing on the VPS and Termux host:
   ```bash
   echo 1 | sudo tee /proc/sys/net/ipv4/tcp_mtu_probing
   ```

4. **Permissions and SELinux Blocks**
   *Problem*: Key-based login fails with `Permission denied (publickey)`.
   *Fix*: Ensure correct directory ownership, permissions (700/600), and double-check Termux SELinux policies if accessing files outside the app's private directories.

---

## Verification Checklist

- [ ] **Wake Lock Active**: Termux wake lock held (persistent Android notification present).
- [ ] **Reachability**: VPS can ping the Termux IP via Tailscale: `tailscale ping <remote-ip>`.
- [ ] **Authentication**: Key-based handshake works without prompting for password:
  `ssh -o ConnectTimeout=5 -i ~/.ssh/id_ed25519 -p 8022 <user>@<remote-ip> 'echo connected'`.
- [ ] **Service Persistence**: Services started natively survive terminal disconnect and are verified using `curl` against the local/forwarded port.

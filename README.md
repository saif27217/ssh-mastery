# SSH Mastery — VPS ↔ Remote Device SSH Pipeline

A complete reference for connecting a Linux VPS to a remote device via SSH, running AI proxy servers, and managing the entire infrastructure. This is the single source of truth for the project.

## Architecture

```
┌─────────────────────┐         Tailscale (100.x.x.x)        ┌──────────────────────────┐
│   VPS (Agent host)  │ ◄──────────────────────────────────► │    Remote device         │
│                     │                                      │                          │
│  Hermes Agent       │   Port 9000 (FastAPI proxy)          │  proxy_server.py         │
│  (local backend)    │ ◄──────────────────────────────────►  │  (Python)                │
│                     │                                      │                          │
│  Terminal env: local│                                      │  SSH daemon: port <sp>   │
│  Tailscale IP       │                                      │  Tailscale IP: <rip>     │
└─────────────────────┘                                      └──────────────────────────┘
```

**Why this setup:**
- Remote device may be behind NAT — cannot accept inbound connections from VPS directly
- Hermes Agent SSH backend requires TERMINAL_SSH_HOST + TERMINAL_SSH_USER to be set (currently using local)
- The AI proxy runs on the remote device and is accessed from the VPS over Tailscale
- Platform-specific pitfalls (e.g., proot-distro killing background processes) are documented below

## Key IPs & Ports

All specific IPs, hostnames, and usernames are kept out of this public repo. Configure them in your local ~/.hermes/config.yaml and .env files.

| Device | Role | Connectivity | SSH Port | Service Ports |
|--------|------|-------------|----------|--------------|
| VPS | Agent host | Tailscale outbound | N/A | N/A |
| Remote device 1 | AI proxy host | Tailscale | <ssh-port> | 9000 (FastAPI proxy), <other-ports> |
| Remote device 2 | AI infrastructure | Tailscale | <ssh-port> (key + password) | <router-port> (AI router), 5432 (PostgreSQL) |
| Remote device 3 | Desktop | Tailscale | CLOSED (no SSH) | 5432 (PostgreSQL only) |

**Host reachability notes:**
- A pingable host may have NO open ports (some devices are reachable via Tailscale but have no SSH server — only PostgreSQL or other services)
- Always scan ports before assuming a service is available
- Scan common ports: for p in 22 2222 8022 20128 3000 5432 80 443 8080; do echo -n "$p: "; timeout 3 bash -c "echo >/dev/tcp/IP/$p" 2>/dev/null && echo OPEN || echo CLOSED; done

## Quick Commands

### From VPS to Remote Device

```bash
# SSH into remote device
ssh -o StrictHostKeyChecking=no <user>@<remote-ip> -p <ssh-port>

# Health check on the proxy
curl http://<remote-ip>:9000/health

# Test API endpoint
curl -s http://<remote-ip>:9000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer *** \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"test"}],"max_tokens":10}'

# Check proxy process
ssh <user>@<remote-ip> -p <ssh-port> 'ps aux | grep proxy_server | grep -v grep'

# Restart proxy
ssh <user>@<remote-ip> -p <ssh-port> 'pkill -f proxy_server.py; sleep 1; cd ~ && python3 proxy_server.py &'
```

### From Remote Device (local)

```bash
# Health check
curl http://127.0.0.1:9000/health

# Start proxy manually
python3 proxy_server.py &
```

## Hermes Configuration

The VPS ~/.hermes/config.yaml has the provider configured:

```yaml
providers:
  my-provider:
    base_url: http://<remote-ip>:9000/v1
    api_key: <your-api-key>
    request_timeout_seconds: 300
    models:
      gpt-4o-mini:
        max_output_tokens: 65536
```

To enable SSH backend (for direct command execution on the remote device), set in ~/.hermes/.env or via environment:

```bash
TERMINAL_SSH_HOST=<remote-ip>
TERMINAL_SSH_USER=<user>
TERMINAL_SSH_PORT=<ssh-port>
TERMINAL_SSH_KEY=<path-to-ssh-key>
TERMINAL_ENV=ssh
```

## Project Structure

```
ssh-mastery/
├── README.md                      # This file — architecture and quick reference
├── AGENTS.md                      # Agent skill: how any AI to use this repo as expert knowledge
├── scripts/
│   ├── start_proxy.sh            # One-command proxy startup (remote device)
│   └── telegram-setup.sh          # Telegram bot setup script
├── termux/
│   ├── proxy_server.py            # Main FastAPI proxy server (patched: thread persistence + memory)
│   └── .env.example               # Template for API key configuration
└── vps-docs/
    └── ...                        # Historical docs from the project
```

## Generic Remote Endpoint Connection Guide

Use this for any remote tool/endpoint (9router, FastAPI, databases, internal APIs) behind a remote host over Tailscale.

### 1. Verify service is running locally on the remote host

```bash
# On remote host via SSH
curl -s http://127.0.0.1:<PORT>/health
ss -tlnp | grep <PORT>
```

If this fails, fix the service first.

### 2. Confirm remote port is unreachable directly

```bash
curl -s http://<remote-ip>:<PORT>/v1/models
# Expected: 401/403 or empty response
```

If this returns data without auth, the service is already public — skip to step 4.

### 3. Create SSH tunnel (local forward)

One-shot test:
```bash
ssh -N -o StrictHostKeyChecking=no -o ConnectTimeout=10 \
  -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
  -o TCPKeepAlive=yes -o ExitOnForwardFailure=yes \
  -L 127.0.0.1:<LOCAL_PORT>:localhost:<REMOTE_PORT> <user>@<remote-ip>
```

Persistent (systemd unit):
```ini
[Unit]
Description=SSH tunnel to <tool> on <remote-ip>
After=network-online.target tailscaled.service
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/ssh \
  -o StrictHostKeyChecking=no \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  -o TCPKeepAlive=yes \
  -o ExitOnForwardFailure=yes \
  -o ConnectTimeout=10 \
  -o BatchMode=yes \
  -N -L 127.0.0.1:<LOCAL_PORT>:localhost:<REMOTE_PORT> <user>@<remote-ip>
Restart=always
RestartSec=3

[Install]
WantedBy=default.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now <name>-tunnel.service
```

### 4. Verify end-to-end

```bash
timeout 3 bash -c 'echo > /dev/tcp/127.0.0.1/<LOCAL_PORT>' && echo ALIVE || echo DEAD

curl -s --max-time 10 http://127.0.0.1:<LOCAL_PORT>/v1/models | head -c 200
```

### 5. If headers arrive but body stalls (Tailscale MTU blackhole)

```bash
# On the REMOTE host
cat /sys/class/net/tailscale0/mtu                  # 1280
cat /proc/sys/net/ipv4/tcp_mtu_probing             # 0 = off

# Fix
echo 1 | sudo tee /proc/sys/net/ipv4/tcp_mtu_probing
echo 'net.ipv4.tcp_mtu_probing = 1' | sudo tee /etc/sysctl.d/99-tcp-mtu-probing.conf
sudo sysctl --system
```

First request after fix takes 6–10 s. Subsequent requests are normal speed.

### 6. Add to Hermes config

```yaml
providers:
  <name>:
    base_url: http://127.0.0.1:<LOCAL_PORT>/v1
    api_key: <key-if-needed>
    request_timeout_seconds: 300
    stale_timeout_seconds: 600
```

Restart the Hermes gateway and test a real completion call.

### 7. Common failure modes

| Symptom | Cause | Fix |
|---------|-------|-----|
| DEAD port, SSH process running | Tunnel bound wrong target or remote service down | Check remote `ss -tlnp`, restart tunnel |
| Headers OK, body stalls after 1–2 s | Tailscale MTU blackhole | Enable `tcp_mtu_probing=1` on remote |
| API key required remotely | Tunnel not in place or pointing at wrong port | Confirm using `127.0.0.1:<LOCAL_PORT>` |
| Tunnel dies after network change | No supervision | systemd `Restart=always`, not nohup/disown |
| transfer closed with outstanding read data remaining | MTU issue (see above) | Fix MTU probing, don’t retry |

## Known Limitations
1. **Tailscale MTU blackhole**: if headers arrive but body stalls with `exit code 18` / `transfer closed with outstanding read data remaining`, enable `tcp_mtu_probing=1` on the remote host.
2. **Proot-distro kills background processes** — always use native Python for persistent services
3. **Tailscale on mobile devices** — the device may go offline; check status before attempting connections
4. **Model tier limits** — some models may fail due to upstream account limitations (not proxy issues)
5. **SSH to remote device** — requires SSH package installed; port varies by platform
6. **Verify config before restart**: after changing any provider `<name>` or `base_url`, restart the Hermes gateway before testing new aliases.
7. **Choosing `9router-op` vs `9router-pc`**: use one canonical mount if both point to the same upstream; duplicate mounts to the same endpoint are redundant.

## Tunnel/Tailscale Troubleshooting

### Headers arrive, body stalls — Tailscale MTU blackhole

Symptom: curl prints the HTTP status line and headers, then hangs until timeout with exit code 18 or transfer closed with outstanding read data remaining.

```bash
# This hangs mid-body:
curl -v http://127.0.0.1:<PORT>/v1/models

# But this often works from the same box:
curl -v http://<remote-ip>:<PORT>/v1/models
```

And the service responds fine locally on the remote host:

```bash
curl -s http://127.0.0.1:20128/v1/models | wc -c   # full response
cat /sys/class/net/tailscale0/mtu                  # 1280
cat /proc/sys/net/ipv4/tcp_mtu_probing             # 0 = off
```

Root cause: Tailscale’s default 1280-byte MTU. With kernel PMTU probing disabled, oversized TCP segments get silently dropped. The kernel never backs off to smaller segments.

Fix on the remote host:

```bash
echo 1 | sudo tee /proc/sys/net/ipv4/tcp_mtu_probing
echo 'net.ipv4.tcp_mtu_probing = 1' | sudo tee /etc/sysctl.d/99-tcp-mtu-probing.conf
sudo sysctl --system
```

First request after the change may take 6–10 s while the path MTU is rediscovered; subsequent requests drop to normal speeds.

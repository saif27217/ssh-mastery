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
- Hermes Agent SSH backend requires `TERMINAL_SSH_HOST` + `TERMINAL_SSH_USER` to be set (currently using `local`)
- The AI proxy runs on the remote device and is accessed from the VPS over Tailscale
- Platform-specific pitfalls (e.g., proot-distro killing background processes) are documented below

## Key IPs & Ports

All specific IPs, hostnames, and usernames are kept out of this public repo. Configure them in your local `~/.hermes/config.yaml` and `.env` files.

| Device | Role | Connectivity | SSH Port | Service Ports |
|--------|------|-------------|----------|--------------|
| VPS | Agent host | Tailscale outbound | N/A | N/A |
| Remote device 1 | AI proxy host | Tailscale | `<ssh-port>` | `9000` (FastAPI proxy), `<other-ports>` |
| Remote device 2 | AI infrastructure | Tailscale | `<ssh-port>` (key + password) | `<router-port>` (AI router), `5432` (PostgreSQL) |
| Remote device 3 | Desktop | Tailscale | **CLOSED** (no SSH) | `5432` (PostgreSQL only) |

**Host reachability notes:**
- A pingable host may have NO open ports (some devices are reachable via Tailscale but have no SSH server — only PostgreSQL or other services)
- Always scan ports before assuming a service is available
- Scan common ports: `for p in 22 2222 8022 20128 3000 5432 80 443 8080; do echo -n "$p: "; timeout 3 bash -c "echo >/dev/tcp/IP/$p" 2>/dev/null && echo OPEN || echo CLOSED; done`

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

The VPS `~/.hermes/config.yaml` has the provider configured:

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

To enable SSH backend (for direct command execution on the remote device), set in `~/.hermes/.env` or via environment:

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
├── proot-backup/
│   └── ...                        # Legacy proot files (reference only — broken)
└── vps-docs/
    └── ...                        # Historical docs from the project
```

## Known Limitations

1. **Proot-distro kills background processes** — always use native Python for persistent services
2. **Tailscale on mobile devices** — the device may go offline; check status before attempting connections
3. **Model tier limits** — some models may fail due to upstream account limitations (not proxy issues)
4. **SSH to remote device** — requires SSH package installed; port varies by platform

## Related Repos

- [ssh-mastery](https://github.com/saif27217/ssh-mastery) — this repo

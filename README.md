# SSH Mastery — VPS ↔ Termux Remote Execution Pipeline

A complete reference for connecting a Linux VPS to an Android device (Termux) via SSH, running AI proxy servers, and managing the entire infrastructure. This is the single source of truth for the project.

## Architecture

```
┌─────────────────────┐         Tailscale (100.x.x.x)        ┌──────────────────────┐
│   Hostinger VPS     │ ◄──────────────────────────────────► │    OnePlus 5 (Termux) │
│  Mumbai, India      │                                      │    Android          │
│                     │                                      │                     │
│  Hermes Agent       │   Port 9000 (FastAPI proxy)          │  oneminai_server.py │
│  (local backend)    │ ◄──────────────────────────────────► │  (uvicorn, Python 3.13)│
│                     │                                      │                     │
│  Terminal env: local│                                      │  SSH daemon: port 8022│
│  Tailscale IP:      │                                      │  Tailscale IP:       │
│  100.92.56.61      │                                      │  100.70.18.84       │
└─────────────────────┘                                      └──────────────────────┘
```

**Why this setup:**
- Termux is behind NAT — cannot accept inbound connections from VPS directly
- Hermes Agent SSH backend requires `TERMINAL_SSH_HOST` + `TERMINAL_SSH_USER` to be set (currently using `local`)
- The 1min.ai proxy runs on Termux (persistent via native Python, not proot-distro) and is accessed from the VPS over Tailscale
- Proot-distro kills all child processes on session exit — **never use it for background services**

## Key IPs & Ports

| Device | Role | Tailscale IP | SSH Port | Service Port |
|--------|------|-------------|----------|-------------|
| VPS (Hostinger) | Agent host | `100.92.56.61` | N/A (outbound only) | N/A |
| Termux (OnePlus 5) | Remote server | `100.70.18.84` | `8022` (Termux SSH) | `9000` (FastAPI) |

## Quick Commands

### From VPS to Termux

```bash
# SSH into Termux
ssh -o StrictHostKeyChecking=no sak@100.70.18.84 -p 8022

# Health check on the proxy
curl http://100.70.18.84:9000/health

# Test API endpoint
curl -s http://100.70.18.84:9000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <API_KEY>" \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"test"}],"max_tokens":10}'

# Check proxy process
ssh sak@100.70.18.84 -p 8022 'ps aux | grep oneminai | grep -v grep'

# Restart proxy
ssh sak@100.70.18.84 -p 8022 'pkill -f oneminai_server.py; sleep 1; cd ~ && python3 oneminai_server.py &'
```

### From Termux (local)

```bash
# Health check
curl http://127.0.0.1:9000/health

# Check logs
journalctl -u hermes-gateway --no-pager -n 50

# Start proxy manually
python3 oneminai_server.py &
```

## Hermes Configuration

The VPS `~/.hermes/config.yaml` has the `1minai-local` provider configured:

```yaml
providers:
  1minai-local:
    base_url: http://100.70.18.84:9000/v1
    api_key: cd316cf34aa09c345d743874d2f6daf834d043af7e8881955497144fbdfac314
    request_timeout_seconds: 300
    models:
      gpt-4o-mini:
        max_output_tokens: 65536
```

To enable SSH backend (for direct command execution on Termux), set in `~/.hermes/.env` or via environment:

```bash
TERMINAL_SSH_HOST=100.70.18.84
TERMINAL_SSH_USER=sak
TERMINAL_SSH_PORT=8022
TERMINAL_SSH_KEY=/home/sak/.ssh/id_ed25519
TERMINAL_ENV=ssh
```

## Project Structure

```
ssh-mastery/
├── README.md                      # This file — architecture and quick reference
├── AGENTS.md                      # Agent skill: how any AI to use this repo as expert knowledge
├── scripts/
│   ├── start_oneminai.sh          # One-command proxy startup (Termux)
│   ├── start_proot_server.sh      # Proot fallback startup (deprecated — see warnings)
│   └── telegram-setup.sh          # Telegram bot setup script
├── termux/
│   ├── oneminai_server.py         # Main FastAPI proxy server (patched: thread persistence + memory)
│   └── .env.oneminai.example      # Template for API key configuration
├── proot-backup/
│   ├── proot_oneminai_server.py   # Original proot-based server (reference only — broken)
│   ├── litellm_stub_proot.py      # LiteLLM stub for proot environment
│   └── install_stub.py            # Stub installation script
└── vps-docs/
    ├── INDEX.md                   # Project index and file map
    ├── VERIFICATION.txt           # Connection verification log
    └── IMPLEMENTATION_SUMMARY.md  # Detailed implementation history
```

## Known Limitations

1. **Proot-distro kills background processes** — always use Termux native Python for persistent services
2. **Tailscale on Termux** — the Android device may go offline; check status before attempting connections
3. **Model tier limits** — `gemini-2.0-flash` and `claude-3-5-sonnet` fail via 1min.ai free tier (account limitation, not proxy issue)
4. **SSH to Termux** — requires Termux:SSH package installed; port 8022 is the default

## Related Repos

- [fastapi-termux-1minAI](https://github.com/saif27217/fastapi-termux-1minAI) — the proxy server alone (clean commit)
- [sak2k-bio/datsutra-app](https://github.com/sak2k-bio/datsutra-app) — canonical repo (supabase branch)

# SSH Mastery — Agent Skill

This repo is the single source of truth for the VPS ↔ Termux SSH pipeline. Any agent that loads this skill can operate the entire infrastructure as an expert.

## TL;DR — The 30-Second Mental Model

```
VPS (Hermes Agent) ──Tailscale──► Termux (1min.ai proxy on port 9000)
      ▲                                    │
      └──── SSH (port 8022) ───────────────┘
```

- **Proxy runs on Termux**: `oneminai_server.py` (FastAPI, Python 3.13, port 9000)
- **Access from VPS**: `http://100.70.18.84:9000/v1`
- **SSH into Termux**: `ssh sak@100.70.18.84 -p 8022`
- **Hermes uses it via**: `1minai-local` provider in `~/.hermes/config.yaml`

## Repo Layout

```
ssh-mastery/
├── AGENTS.md              ← YOU ARE HERE (this file)
├── README.md              ← Architecture + quick commands
├── scripts/
│   ├── start_oneminai.sh  ← Start the proxy on Termux
│   ├── start_proot_server.sh  ← Deprecated! Do NOT use. See "Critical Pitfalls".
│   └── telegram-setup.sh  ← Telegram bot setup
├── termux/
│   ├── oneminai_server.py ← Main proxy server (patched for thread + memory)
│   └── .env.oneminai.example ← API key template
├── proot-backup/          ← Legacy proot files. Reference only. Do NOT deploy these.
└── vps-docs/              ← Historical docs from the project
```

## Critical Pitfalls (Read First)

### 1. NEVER use proot-distro for background services
proot-distro has `--kill-on-exit` — it kills ALL child processes when the login session ends. This means:
- **Bad**: `proot-distro login -- bash -c "uvicorn server.py &"` → dies on logout
- **Good**: Termux native Python: `python3 oneminai_server.py &` → survives
- The `proot-backup/` directory exists only as historical reference.

### 2. Tailscale connectivity is not guaranteed
The Android device may go offline. Always verify reachability before attempting operations:
```bash
# From VPS, check if Termux is reachable
tailscale ping 100.70.18.84   # or use the ping tool
curl --connect-timeout 5 http://100.70.18.84:9000/health
```

### 3. SSH to Termux requires Termux:SSH package
Termux does not ship with an SSH daemon by default. You need:
- Install `termux-api` and `openssh` in Termux
- Start SSH: `sshd` (runs on port 8022 by default)
- The SSH key is `~/.ssh/id_ed25519` on the VPS, paired with the Termux public key

### 4. API key must match exactly
The key in `config.yaml` (VPS) and `.env` (Termux) must be identical:
- Length: 64 characters
- Pattern: starts with `cd316c`, ends with `ac314`
- Mismatch causes `invalid_api_key` errors

### 5. Thread persistence lives on Termux, not in git
The file `~/.hermes_conversation_ids.json` on Termux stores conversation UUIDs. This is auto-created by the proxy and should NOT be committed to git (it's in `.gitignore`).

## How to Operate the Proxy

### Start the proxy (from VPS)
```bash
ssh sak@100.70.18.84 -p 8022 'cd ~ && python3 oneminai_server.py &'
```

### Check health
```bash
# From VPS
curl http://100.70.18.84:9000/health

# From Termux (local)
curl http://127.0.0.1:9000/health
```

### Restart the proxy
```bash
ssh sak@100.70.18.84 -p 8022 'pkill -f oneminai_server.py; sleep 1; cd ~ && python3 oneminai_server.py &'
```

### Check if running
```bash
ssh sak@100.70.18.84 -p 8022 'ps aux | grep oneminai | grep -v grep'
```

### Test an API call
```bash
curl -s http://100.70.18.84:9000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer *** \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"test"}],"max_tokens":10}'
```

## Hermes Integration

### Current config (VPS `~/.hermes/config.yaml`)
The `1minai-local` provider is already configured. Model aliases:
- `1m` → `gpt-4o-mini` via 1min.ai proxy (works)
- `1m-flash` → `gemini-2.0-flash` via 1min.ai proxy (fails — tier limit)
- `1m-sonnet` → `claude-3-5-sonnet` via 1min.ai proxy (fails — tier limit)

### To enable SSH backend for Hermes
Set these environment variables (in `~/.hermes/.env` or system env):
```bash
TERMINAL_SSH_HOST=100.70.18.84
TERMINAL_SSH_USER=sak
TERMINAL_SSH_PORT=8022
TERMINAL_SSH_KEY=/home/sak/.ssh/id_ed25519
TERMINAL_ENV=ssh
```

Then restart the Hermes gateway:
```bash
systemctl restart hermes-gateway
```

The SSH backend (`tools/environments/ssh.py`) uses ControlMaster for persistent connections, auto-detects remote home, and syncs files via SCP/tar. It requires both `ssh_host` AND `ssh_user` to be set.

## Server Code — oneminai_server.py

This is the main FastAPI proxy. Key features:

### Thread Persistence
- Uses `~/.hermes_conversation_ids.json` to store UUIDs per user
- Each new user gets a fresh UUID; subsequent calls reuse it
- Enables multi-turn conversations within a thread

### Account-Level Memory
- Sends `withMemories: true` in every API request to 1min.ai
- Memory is tied to the **account** (API key), not individual conversations
- Persists across sessions, devices, and apps using the same key
- Manage memory entries via the 1min.ai web UI

### API Endpoints
- `POST /v1/chat/completions` — OpenAI-compatible chat endpoint
- `GET /health` — Health check (returns `{"status":"healthy"}`)

### Payload Structure
```json
{
  "model": "gpt-4o-mini",
  "messages": [{"role": "user", "content": "Hello"}],
  "max_tokens": 10,
  "conversation_id": "uuid-here"  // optional, auto-managed
}
```

### What Gets Sent to 1min.ai
```json
{
  "model": "...",
  "messages": [...],
  "withMemories": true,
  "conversationId": "uuid-here"
}
```

## Troubleshooting

### "All providers unavailable"
- Check if the proxy is running: `curl http://100.70.18.84:9000/health`
- If healthy, the issue is likely a 1min.ai tier limitation for that model
- Models known to fail: `gemini-2.0-flash`, `claude-3-5-sonnet`

### "invalid_api_key"
- Verify the API key in `config.yaml` matches the one in Termux `.env`
- Both must be 64 characters, identical content

### Connection timed out
- Check Tailscale connectivity: `tailscale ping 100.70.18.84`
- The Android device may be offline or have Tailscale disabled
- Try pinging from the VPS first before attempting SSH

### Proxy not responding after restart
- Check if the process is running: `ps aux | grep oneminai`
- If not, start it: `python3 oneminai_server.py &`
- If it starts then dies, check for port conflicts or syntax errors

### Hermes can't reach the proxy
- Verify `config.yaml` has correct `base_url`: `http://100.70.18.84:9000/v1`
- Restart the gateway: `systemctl restart hermes-gateway`
- Check gateway logs: `journalctl -u hermes-gateway --no-pager -n 50`

## Git Workflow

### Pushing changes
```bash
# On VPS (for this repo)
cd ~/.hermes/repos/ssh-mastery
git add .
git commit -m "description"
git push
```

### Pulling latest
```bash
cd ~/.hermes/repos/ssh-mastery
git pull
```

### Syncing proxy from git to Termux
```bash
# After committing changes on VPS:
scp ~/.hermes/repos/ssh-mastery/termux/oneminai_server.py sak@100.70.18.84:/data/data/com.termux/files/home/ -P 8022
ssh sak@100.70.18.84 -p 8022 'pkill -f oneminai_server.py; sleep 1; cd ~ && python3 oneminai_server.py &'
```

## Network Diagram

```
Internet
    │
    ▼
┌──────────────────┐     Tailscale wireguard      ┌─────────────────────┐
│  Hostinger VPS    │ ◄──────────────────────────► │  OnePlus 5 (Termux) │
│  76.13.243.223   │     100.92.56.61             │  100.70.18.84       │
│                  │         ══════════            │                     │
│  Hermes Gateway  │         │  Port 9000          │  oneminai_server.py │
│  (systemd)       │ ──────► │  FastAPI/uvicorn    │  (Python 3.13)      │
│                  │         │                     │                     │
│  Terminal: local │         │                     │  SSH: port 8022     │
│  Tailscale IP    │         │                     │  Termux:SSH         │
│  100.92.56.61   │         │                     │  Tailscale IP       │
└──────────────────┘         │                     │  100.70.18.84       │
                             │                     └─────────────────────┘
                             │
                      Port 8022 (SSH)
                      sak@100.70.18.84
```

## Memory Architecture

1min.ai has two memory tiers:

| Tier | Scope | Resettable? | Managed By |
|------|-------|-------------|------------|
| Conversation History | Single thread (`conversationId`) | Yes (`clearHistory: true`) | Auto |
| Account Memory | All threads, all sessions | No (manual) | 1min.ai web UI |

The proxy sends `withMemories: true` to enable account memory. This means the AI remembers things introduced in previous turns even across separate API calls.

## File Locations Reference

| File | Location | Purpose |
|------|----------|---------|
| Proxy server | Termux: `~/oneminai_server.py` | Main FastAPI proxy |
| API key (Termux) | Termux: `~/.env` | ONEMINAI_API_KEY |
| API key (VPS) | VPS: `~/.hermes/config.yaml` → `1minai-local.api_key` | Provider config |
| Thread storage | Termux: `~/.hermes_conversation_ids.json` | UUID per user |
| Hermes config | VPS: `~/.hermes/config.yaml` | Provider + terminal settings |
| SSH key | VPS: `~/.ssh/id_ed25519` | Key for SSH to Termux |
| Gateway service | VPS: `systemctl status hermes-gateway` | Hermes gateway process |

# SSH Mastery — Agent Skill

This repo is the single source of truth for the VPS ↔ remote-device SSH pipeline. Any agent that loads this skill can operate the entire infrastructure as an expert.

## TL;DR — The 30-Second Mental Model

```
VPS (Hermes Agent) ──Tailscale──► Remote device (AI proxy on port 9000)
      ▲                                    │
      └──── SSH (port 8022) ───────────────┘
```

- **Proxy runs on remote device**: AI proxy (FastAPI, Python 3.x, port 9000)
- **Access from VPS**: `http://<remote-ip>:9000/v1`
- **SSH into remote device**: `ssh <user>@<remote-ip> -p <ssh-port>`
- **Hermes uses it via**: provider in `~/.hermes/config.yaml`

## Repo Layout

```
ssh-mastery/
├── AGENTS.md              ← YOU ARE HERE (this file)
├── README.md              ← Architecture + quick commands
├── scripts/
│   ├── start_proxy.sh   ← Start the proxy on remote device
│   └── telegram-setup.sh  ← Telegram bot setup
├── termux/
│   ├── proxy_server.py    ← Main proxy server (patched for thread + memory)
│   └── .env.example       ← API key template
├── proot-backup/          ← Legacy proot files. Reference only. Do NOT deploy these.
└── vps-docs/              ← Historical docs from the project
```

## Critical Pitfalls (Read First)

### 1. NEVER use proot-distro for background services
proot-distro has `--kill-on-exit` — it kills ALL child processes when the login session ends. This means:
- **Bad**: `proot-distro login -- bash -c "uvicorn server.py &"` → dies on logout
- **Good**: Native Python: `python3 proxy_server.py &` → survives
- The `proot-backup/` directory exists only as historical reference.

### 2. Tailscale connectivity is not guaranteed
Devices may go offline. Always verify reachability before attempting operations:
```bash
# From VPS, check if device is reachable
tailscale ping <remote-ip>   # or
ping -c 2 <remote-ip>
```

**Key insight:** A host that responds to ping may have NO SSH ports open at all (e.g., a desktop node reachable via Tailscale but with no SSH server — only PostgreSQL). Always scan ports before assuming SSH is available.

### 3. SSH to remote devices requires an SSH daemon
Some platforms (e.g., Termux) do not ship with an SSH daemon by default. You need:
- Install the SSH package (e.g., `openssh` on Termux)
- Start the daemon: `sshd` (runs on port 8022 by default)
- The SSH key is `~/.ssh/id_ed25519` on the VPS, paired with the remote device's public key

### 4. API key must match exactly
The key in `config.yaml` (VPS) and `.env` (remote) must be identical. Mismatch causes `invalid_api_key` errors.

### 5. Thread persistence lives on the remote device, not in git
Files like `~/.conversation_ids.json` store session UUIDs. These are auto-created by the proxy and should NOT be committed to git (they're in `.gitignore`).

### 6. SSH key auth is preferred over password
When passwordless SSH key auth is set up, it eliminates TTY/prompt issues entirely. For new hosts, always copy the public key first:
```bash
ssh-copy-id <user>@<host>  # or manually append to ~/.ssh/authorized_keys
```

### 7. Port scanning rule: one timeout is enough
If `echo >/dev/tcp/HOST/PORT` hangs (times out), do NOT retry. The port is either firewalled (DROP rule) or no service is listening. Re-scanning won't change the result until the remote end changes. Move to the next diagnostic step.

## How to Operate the Proxy

### Start the proxy (from VPS)
```bash
ssh <user>@<remote-ip> -p <ssh-port> 'cd ~ && python3 proxy_server.py &'
```

### Check health
```bash
# From VPS
curl http://<remote-ip>:9000/health

# From remote device (local)
curl http://127.0.0.1:9000/health
```

### Restart the proxy
```bash
ssh <user>@<remote-ip> -p <ssh-port> 'pkill -f proxy_server.py; sleep 1; cd ~ && python3 proxy_server.py &'
```

### Check if running
```bash
ssh <user>@<remote-ip> -p <ssh-port> 'ps aux | grep proxy_server | grep -v grep'
```

### Test an API call
```bash
curl -s http://<remote-ip>:9000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <api-key>" \
  -d '{"model":"gpt-4o-mini","messages":[{"role":"user","content":"test"}],"max_tokens":10}'
```

## Hermes Integration

### Current config (VPS `~/.hermes/config.yaml`)
The provider is already configured. Model aliases:
- `m1` → model A via proxy (works)
- `m2` → model B via proxy (may fail — tier limit)

### To enable SSH backend for Hermes
Set these environment variables (in `~/.hermes/.env` or system env):
```bash
TERMINAL_SSH_HOST=<remote-ip>
TERMINAL_SSH_USER=<user>
TERMINAL_SSH_PORT=<ssh-port>
TERMINAL_SSH_KEY=<path-to-ssh-key>
TERMINAL_ENV=ssh
```

Then restart the Hermes gateway:
```bash
systemctl restart hermes-gateway
```

The SSH backend (`tools/environments/ssh.py`) uses ControlMaster for persistent connections, auto-detects remote home, and syncs files via SCP/tar. It requires both `ssh_host` AND `ssh_user` to be set.

## Server Code — proxy_server.py

This is the main FastAPI proxy. Key features:

### Thread Persistence
- Uses `~/.conversation_ids.json` to store UUIDs per user
- Each new user gets a fresh UUID; subsequent calls reuse it
- Enables multi-turn conversations within a thread

### Account-Level Memory
- Sends `withMemories: true` in every API request to the upstream
- Memory is tied to the **account** (API key), not individual conversations
- Persists across sessions, devices, and apps using the same key
- Manage memory entries via the upstream web UI

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

## Troubleshooting

### SSH Diagnostic Order

When an SSH connection fails, follow this exact sequence:

```bash
# 1. Host reachable?
ping -c 2 <IP>               # ICMP works? Host is alive on network
tailscale ping <IP>           # Tailscale peer? Device is on tailnet

# 2. Port open?
timeout 3 bash -c "echo > /dev/tcp/<IP>/22" 2>/dev/null && echo OPEN || echo CLOSED

# 3. Verbose handshake (watch where it hangs)
ssh -v user@<IP>
```

**Where it hangs tells you the cause:**
| Symptom | Cause | Fix |
|---------|-------|-----|
| `Connection established` → hangs at KEX | Server-side: sshd overloaded, slow crypto | Restart sshd on remote |
| `KEX_ECDH_REPLY received` → auth fails | Authentication: wrong key/password | Add key or try password |
| `password:` prompt (no TTY) | Need paramiko or sshpass | Use Python paramiko |
| Connection refused | No SSH server or wrong port | Install SSH or scan ports |
| Connection timed out | Port blocked by firewall | Check iptables/UFW on remote |

**Critical: Do NOT escalate retries on timeout.** If port 22 times out once, it will time out every time until the remote end changes.

### Password Auth Without a TTY (paramiko)

When `sshpass` and `expect` are unavailable (common on stripped-down systems or no-root environments), use paramiko (already installed with Hermes):

```python
import paramiko
client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect('<host>', username='<user>', password='<password>', timeout=10)

# Run commands
stdin, stdout, stderr = client.exec_command('hostname && whoami')
print(stdout.read().decode())

# Check processes
stdin, stdout, stderr = client.exec_command('ss -tlnp | grep <port>')
print(stdout.read().decode())

client.close()
```

**Quoting pitfall:** Python string escapes in exec_command can break with nested quotes. Solutions:
- Simple commands: `client.exec_command('ls -la')` works fine
- Complex pipes/variables: write a script file to remote, then execute it
- Use heredocs via `stdin.write()` + `channel.shutdown_write()`

### Port Scanning via paramiko

```python
stdin, stdout, stderr = client.exec_command('''for port in 22 2222 8022 20128 3000 5432; do
  echo -n "Port $port: "
  timeout 3 bash -c "echo >/dev/tcp/127.0.0.1/$port" 2>/dev/null && echo OPEN || echo CLOSED
done''')
print(stdout.read().decode())
```

### Starting Remote Background Processes via paramiko

```python
transport = client.get_transport()
chan = transport.open_session()
chan.set_combine_stderr(True)
chan.exec_command('cd /home/user && PORT=20128 nohup node server.js > /tmp/log 2>&1 & echo STARTED')
import time; time.sleep(2)
print(chan.recv(1024).decode())
chan.close()
```

Note: Starting background processes via exec_command can be unreliable with `nohup`/`&`. The `transport.open_session()` approach works better.

### SSH Tunnel for Service Auth Bypass

Some services (like AI routers) require auth for remote API access but trust localhost connections. Create an SSH tunnel to bypass this:

```bash
# One-shot tunnel: local:<lp> → remote:<rp> (use terminal(background=true))
ssh -N -L <local-port>:localhost:<remote-port> user@remote_host

# Then point providers at http://127.0.0.1:<local-port>/v1
```

**Persistent tunnel script** (`~/.hermes/scripts/service-tunnel.sh`):
```bash
#!/bin/bash
while true; do
  ssh -o StrictHostKeyChecking=no -o BatchMode=yes \
    -o ServerAliveInterval=15 -o ServerAliveCountMax=3 \
    -o ExitOnForwardFailure=yes \
    -N -L <local-port>:localhost:<remote-port> user@remote_host
  sleep 3
done
```

Start with `terminal(background=true)` — do NOT use nohup/disown in foreground commands as they're blocked.

### Config Management for Hermes Providers

After setting up a tunnel, update the provider URL:
```bash
# With hermes CLI (preferred)
hermes config set providers.<name>.base_url http://127.0.0.1:<local-port>/v1

# With sed (requires user approval)
sed -i 's|old_url|http://127.0.0.1:<local-port>/v1|' ~/.hermes/config.yaml
```

### "All providers unavailable"
- Check if the proxy is running: `curl http://<remote-ip>:9000/health`
- If healthy, the issue is likely an upstream tier limitation for that model
- Models known to fail: check upstream provider documentation

### "invalid_api_key"
- Verify the API key in `config.yaml` matches the one in remote `.env`
- Both must be identical

### Connection timed out
- Check Tailscale connectivity: `tailscale ping <remote-ip>`
- The remote device may be offline or have Tailscale disabled
- Try pinging from the VPS first before attempting SSH

### Proxy not responding after restart
- Check if the process is running: `ps aux | grep proxy`
- If not, start it: `python3 proxy_server.py &`
- If it starts then dies, check for port conflicts or syntax errors

### Hermes can't reach the proxy
- Verify `config.yaml` has correct `base_url`: `http://<remote-ip>:9000/v1`
- Restart the gateway: `systemctl restart hermes-gateway`
- Check gateway logs: `journalctl -u hermes-gateway --no-pager -n 50`

## Git Workflow

### Pushing changes
```bash
# On VPS
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

### Syncing proxy from git to remote device
```bash
# After committing changes on VPS:
scp ~/.hermes/repos/ssh-mastery/termux/proxy_server.py <user>@<remote-ip>:/path/to/home/ -P <ssh-port>
ssh <user>@<remote-ip> -p <ssh-port> 'pkill -f proxy_server.py; sleep 1; cd ~ && python3 proxy_server.py &'
```

## Network Diagram

```
┌─────────────────────┐         Tailscale wireguard        ┌──────────────────────────┐
│   VPS (Agent host)  │ ◄──────────────────────────────►  │ Remote device            │
│                     │                                    │                          │
│  Hermes Gateway     │   Port 9000 (FastAPI proxy)        │  proxy_server.py         │
│  (systemd)          │ ◄─────────────────────────────────►│  (Python)                │
│                     │                                    │                          │
│  Terminal: local    │                                    │  SSH daemon: port <sp>   │
│  Tailscale IP       │                                    │  Tailscale IP: <rip>     │
└─────────────────────┘                                    └──────────────────────────┘
                                                           │
                                                    Port <sp> (SSH)
                                                    <user>@<remote-ip>
```

## Memory Architecture

The upstream provider has two memory tiers:

| Tier | Scope | Resettable? | Managed By |
|------|-------|-------------|------------|
| Conversation History | Single thread (`conversationId`) | Yes (`clearHistory: true`) | Auto |
| Account Memory | All threads, all sessions | No (manual) | Upstream web UI |

The proxy sends `withMemories: true` to enable account memory. This means the AI remembers things introduced in previous turns even across separate API calls.

## File Locations Reference

| File | Location | Purpose |
|------|----------|---------|
| Proxy server | Remote: `~/proxy_server.py` | Main FastAPI proxy |
| API key (remote) | Remote: `~/.env` | Upstream API key |
| API key (VPS) | VPS: `~/.hermes/config.yaml` → provider config | Provider config |
| Thread storage | Remote: `~/.conversation_ids.json` | UUID per user |
| Hermes config | VPS: `~/.hermes/config.yaml` | Provider + terminal settings |
| SSH key | VPS: `~/.ssh/id_ed25519` | Key for SSH to remote |
| Gateway service | VPS: `systemctl status hermes-gateway` | Hermes gateway process |

# SSH Mastery — Agent Skill

This repo is the **single source of truth** for the agent’s behavior when connecting any remote service over Tailscale and SSH. Every workflow step described here is mandatory unless the user explicitly overrides it.

Related canonical repo: `tunnel-mastery` (topologies, systemd templates, troubleshooting).

## Identity and Role

This skill applies when the agent is:
- exposing any remote service (AI router, FastAPI, Node, database, internal API) to the local Hermes environment
- operating SSH tunnels (localhost-forwards) to bypass remote auth requirements
- diagnosing Tailscale connectivity, SSH handshake, or mid-stream stall failures
- updating remote references, README, or AGENTS files in this repo and pushing
- asked by the user to connect, verify, extend, or document any remote endpoint

This skill does **not** apply to generic SSH to hosts that do not run the project’s services. For those, use the standard SSH diagnosis order.

## Absolute Rules

1. Read `README.md` before acting. If this `AGENTS.md` and `README.md` conflict, `AGENTS.md` wins.
2. Do **not** push any file that contains real IPs, hostnames, usernames, passwords, tokens, or keys. Sanitize placeholders first: `<remote-ip>`, `<user>`, `<ssh-port>`, `<PORT>`, `<LOCAL_PORT>`.
3. Do **not** edit `~/.hermes/config.yaml` directly. Tell the user the exact YAML to paste or use `hermes config set`.
4. Do **not** use nohup/disown for long-running foreground commands. Use `terminal(background=true)` or a systemd unit.
5. Do **not** retry a probe that already failed without changing the probe itself. Move through the decision tree.
6. Do **not** start an SSH tunnel before confirming the remote service is healthy locally.
7. Do **not** expose service ports to the tailnet unless the user explicitly requires direct access. Prefer tunnel.
8. Prefer the smallest, local fix over a cross-file architecture change.
9. Prefer reusing existing paths and naming in this repo over inventing new ones.
10. After edits to anything affecting runtime (config, tunnel, service), verify with a real call, not a port scan alone.

## Diagnostic Decision Tree

Follow in this order. Stop at the first failing step and fix it before continuing.

### 1. Is the remote host reachable?
```bash
tailscale ping <remote-ip>
```
If this fails: verify Tailscale status, device power, and network selection. Do not proceed to SSH.

### 2. Is SSH available?
```bash
timeout 3 bash -c 'echo > /dev/tcp/<remote-ip>/22' && echo OPEN || echo CLOSED
```
If CLOSED: check sshd status on remote host or scan alternate ports. Do not retry the same port.

### 3. Can you SSH in?
```bash
ssh -v -o StrictHostKeyChecking=no -o ConnectTimeout=10 <user>@<remote-ip>
```
- Hangs at KEX: restart sshd on remote.
- `password:` prompt: use paramiko template (see below).
- Auth failure: verify authorized_keys.

### 4. Is the remote service healthy?
```bash
curl -s http://127.0.0.1:<PORT>/health
ss -tlnp | grep <PORT>
```
Fix the service before tunneling to it.

### 5. Is the remote port accessible directly?
```bash
curl -s http://<remote-ip>:<PORT>/v1/models
```
401/403/empty = expected; full response = already public.

### 6. Does the tunnel fail with mid-stream stall?

Symptom: headers arrive, body dies, `exit code 18` / `transfer closed with outstanding read data remaining`.

Run on **remote host**:
```bash
cat /sys/class/net/tailscale0/mtu                  # 1280
cat /proc/sys/net/ipv4/tcp_mtu_probing             # 0 = off
```

Fix on **remote host**:
```bash
echo 1 | sudo tee /proc/sys/net/ipv4/tcp_mtu_probing
echo 'net.ipv4.tcp_mtu_probing = 1' | sudo tee /etc/sysctl.d/99-tcp-mtu-probing.conf
sudo sysctl --system
```

Do **not** try HTTP version switches, MTU lowering alone, or SSH pipe workarounds for this — they do not work. The fix is kernel PMTU probing, on **both** sides of the link when possible.

### 7. Hermes config
Add/replace provider entry under `providers:` pointing at `http://127.0.0.1:<LOCAL_PORT>/v1`. Tell user the YAML block to paste, then restart Hermes.

## Tunnel Creation

### One-shot test
```bash
ssh -N -o StrictHostKeyChecking=no -o ConnectTimeout=10 \
  -o ServerAliveInterval=30 -o ServerAliveCountMax=3 \
  -o TCPKeepAlive=yes -o ExitOnForwardFailure=yes \
  -L 127.0.0.1:<LOCAL_PORT>:localhost:<REMOTE_PORT> <user>@<remote-ip>
```

### Persistent (systemd)
Use `tunnel-mastery` unit template. Place at `/etc/systemd/system/<name>-tunnel.service`.
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

### Watchdog alternative (no systemd)
`tunnel-mastery` includes `scripts/tunnel-watchdog.py`. Use only when systemd is unavailable.

## SSH via Paramiko (No TTY / Password)

```python
import paramiko

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect('<remote-ip>', username='<user>', password='<password>', timeout=10)

stdin, stdout, stderr = client.exec_command('hostname && whoami')
print(stdout.read().decode())

stdin, stdout, stderr = client.exec_command('ss -tlnp | grep <PORT>')
print(stdout.read().decode())

client.close()
```

Quoting rules:
- Simple commands: `client.exec_command('ls -la')`
- Complex pipes/variables: write a script file first, then execute it
- Write files: `stdin.write(b'...'); stdin.channel.shutdown_write()`

## Hermes Config Rules

1. Edit via `hermes config set providers.<name>.base_url http://127.0.0.1:<LOCAL_PORT>/v1`
2. Do **not** directly edit `~/.hermes/config.yaml`
3. After config changes: restart Hermes gateway, then run a real completion call through the new provider.
4. If a stale `name:` line or orphan key exists for a provider, remove it; do not leave dangling YAML.

## Repo Hygiene (Public Repo)

Before any commit or push to `ssh-mastery` or `tunnel-mastery`:
- Replace all specific IPs with `<remote-ip>` / `<vps-ip>` placeholders
- Replace usernames with `<user>`
- Remove passwords, tokens, keys, and secrets (including JSON values of `api_key`, `Authorization`, `Bearer`, `x-api-key`, cookies)
- Replace hardcoded ports with `<PORT>` / `<LOCAL_PORT>` / `<ssh-port>`
- Do not leave triple-dot redacted fragments that imply a real key existed (`sk-d67...f9b8`); replace with `<api-key>` or remove the example
- Validate: `grep -nE '([0-9]{1,3}\.){3}[0-9]{1,3}' README.md AGENTS.md docs/*.md`
- Validate: `grep -nE '(api_key|password|Bearer|token|secret)[^:]*:[^<]' README.md AGENTS.md docs/*.md`

## Failure Modes

| Symptom | Cause | Fix |
|---------|-------|-----|
| `DEAD` port, SSH running | Tunnel pointing at wrong target or remote service down | Check remote `ss -tlnp`, restart tunnel |
| Headers OK, body stalls after 1–2 s | Tailscale MTU blackhole | Enable `tcp_mtu_probing=1` on remote |
| API key required remotely | Tunnel not reachable or wrong port | Use `127.0.0.1:<LOCAL_PORT>` |
| Tunnel dies after network change | No supervision | systemd `Restart=always` |
| `transfer closed with outstanding read data remaining` | MTU issue | Fix MTU probing, do not retry |

## Update / Push Workflow

1. Edit local checkout of `ssh-mastery` or `tunnel-mastery`.
2. Run sanitization grep checks (above).
3. Commit with a descriptive message. Push only after checks pass.
4. Tell the user the push URL and commit hash.

## Cross-References

- `tunnel-mastery`: topologies, systemd unit template, decision tree for tunnel stealth-death, MTU troubleshooting
- Local skill `~/.hermes/skills/ssh-mastery/`: operational details for 9router and ammara-1 (private)

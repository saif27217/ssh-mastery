# SSH Mastery — VPS ↔ Remote Asset Access

Principles and recipes for exposing any remote service over Tailscale and SSH to your local Hermes agent, safely and repeatably. This repo is the single source of truth for the agent workflow. Companion `tunnel-mastery` covers topology, service supervision, and advanced patterns.

**Audience:** agents and operators who need to connect, verify, and document remote endpoints without hardcoding secrets or breaking public repos.

## Architecture

```
VPS (Hermes Agent) ──Tailscale──► Remote host
      ▲                                    │
      └──── SSH (port 8022) ───────────────┘

Remote service (any tool/endpoint) binds to localhost or 0.0.0.0:<PORT> on the remote host.
Hermes reaches it through:
  1. direct Tailscale IP, or
  2. SSH tunnel mapping remote localhost:<PORT> → local 127.0.0.1:<LOCAL_PORT>
```

**Why this setup:**
- Remote assets may be behind NAT, firewalled, or require auth from localhost only
- Tailscale is the transport; SSH is the access layer
- Always prefer localhost-bound services with an SSH tunnel over exposing ports to the tailnet

## What This Repo Covers

- Diagnostic order for Tailscale reachability and SSH failures
- One-shot and systemd-supervised tunnel creation
- Hermes provider configuration for tunnel endpoints
- The Tailscale MTU blackhole failure mode and fix
- SSH command patterns that do not hang (`timeout`, `BatchMode=yes`, no retries)
- Paramiko templates for password auth and file transfer without TTY

## What `tunnel-mastery` Covers

- Tunnel topologies (local forward, remote forward, dynamic SOCKS)
- systemd unit templates with restart policies
- Persistent tunnel supervision, health checks, and watchdog scripts
- Troubleshooting decision trees for tunnel stealth-death and peer flapping

## Known Limitations

1. **Tailscale MTU blackhole**: if headers arrive but body stalls with `exit code 18` / `transfer closed with outstanding read data remaining`, enable `tcp_mtu_probing=1` on the remote host.
2. **Proot-distro kills background processes**: always use native Python for persistent services.
3. **Tailscale on mobile devices**: the device may go offline; verify reachability before every operation.
4. **SSH to remote device**: requires SSH server installed; port varies by platform.
5. **Verify config before restart**: after changing provider `base_url`, restart the Hermes gateway before testing new aliases.
6. **Avoid duplicate mounts**: if two providers point to the same upstream endpoint, consolidate to one canonical mount.

## Sanitization (Public Repo Rule)

All specific IPs, hostnames, usernames, passwords, and tokens are represented as placeholders (`<remote-ip>`, `<user>`, `<ssh-port>`, `<PORT>`, `<LOCAL_PORT>`). These files are safe to commit and share.

Local operational details (real IPs, keys, credentials) stay in local agent skills and environment files, never in this repo.

## Quick Reference

| Action | Command / Pattern |
|--------|-------------------|
| Test service locally on remote host | `curl -s http://127.0.0.1:<PORT>/health` |
| Verify port is unreachable directly | `curl -s http://<remote-ip>:<PORT>/v1/models` |
| One-shot tunnel test | `ssh -N -o StrictHostKeyChecking=no -o ConnectTimeout=10 -L 127.0.0.1:<LP>:localhost:<RP> <user>@<remote-ip>` |
| Persistent tunnel (systemd) | See `tunnel-mastery` for unit template |
| Verify tunnel end-to-end | `curl -s --max-time 10 http://127.0.0.1:<LP>/v1/models \| head -c 200` |
| MTU blackhole check (remote) | `cat /sys/class/net/tailscale0/mtu && cat /proc/sys/net/ipv4/tcp_mtu_probing` |
| MTU blackhole fix (remote) | `echo 1 \| sudo tee /proc/sys/net/ipv4/tcp_mtu_probing` + `/etc/sysctl.d/99-tcp-mtu-probing.conf` |
| Hermes provider block | See "Hermes Provider Config" below |
| SSH paramiko (password, no TTY) | See `AGENTS.md` |

## Hermes Provider Config

```yaml
providers:
  <name>:
    base_url: http://127.0.0.1:<LOCAL_PORT>/v1
    api_key: <key-if-needed>
    request_timeout_seconds: 300
    stale_timeout_seconds: 600
    models:
      <model-id>:
        max_output_tokens: 65536
        timeout_seconds: 600
```

Restart Hermes gateway after config changes:
```bash
systemctl restart hermes-gateway
```

## Failure Modes

| Symptom | Cause | Fix |
|---------|-------|-----|
| DEAD port, SSH process running | Tunnel pointing at wrong target or remote service down | Check remote `ss -tlnp`, restart tunnel |
| Headers OK, body stalls after 1–2 s | Tailscale MTU blackhole | Enable `tcp_mtu_probing=1` on remote |
| API key required remotely | Tunnel not in place or pointing at wrong port | Confirm using `127.0.0.1:<LOCAL_PORT>` |
| Tunnel dies after network change | No supervision | systemd `Restart=always`, not nohup/disown |
| `transfer closed with outstanding read data remaining` | MTU issue | Fix MTU probing, do not retry |

## Repo Layout

```
ssh-mastery/
├── README.md          ← Human and agent reference (this file)
├── AGENTS.md          ← Runtime skill for any agent loading this repo
├── scripts/           ← Example automation scripts
└── termux/            ← Reference implementations (e.g. proxy_server.py)
```

`AGENTS.md` is the authoritative source of truth for agent behavior. If this file and `AGENTS.md` conflict, `AGENTS.md` wins.

## Related Repos

- [ssh-mastery](https://github.com/saif27217/ssh-mastery) — this repo
- [tunnel-mastery](https://github.com/saif27217/tunnel-mastery) — tunnel topologies, systemd templates, troubleshooting

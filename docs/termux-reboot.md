---
name: termux-reboot
description: "Full post-reboot recovery workflow for Termux (Android). Heals SSH, starts services, restores tunnels. Run after any Termux/phone reboot."
category: devops
---

# Termux Reboot Recovery

Complete workflow to heal Termux after a phone reboot. Termux has no systemd — all services die on reboot and must be manually restarted.

## When to Run

- Phone rebooted or Termux was killed
- `curl http://100.70.18.84:9000/health` fails
- SSH works but services are down
- Tunnel watchdog alerts on termux-llm

## Prerequisites

- VPS has Tailscale access to Termux (`100.70.18.84`)
- SSH key at `~/.ssh/id_ed25519` (port 8022)
- Termux:SSH app installed on Android

## Recovery Workflow

### Step 1: Verify SSH connectivity

```bash
ssh -o ConnectTimeout=10 100.70.18.84 -p 8022 hostname
```

Expected: returns `localhost`. If fails → check Tailscale, device power, Termux:SSH app.

### Step 2: Check what's running

```bash
ssh 100.70.18.84 -p 8022 'ps aux | grep -E "oneminai|uvicorn|9router|node" | grep -v grep'
```

After reboot: empty output (everything dead).

### Step 3: Start 1minai proxy (port 9000)

```bash
ssh 100.70.18.84 -p 8022 'mkdir -p ~/tmp && cd ~ && nohup python3 oneminai_server.py > ~/tmp/oneminai.log 2>&1 &'
sleep 3
ssh 100.70.18.84 -p 8022 'curl -s http://localhost:9000/health'
```

**Pitfall:** Termux has no `/tmp` — use `~/tmp` instead.

**Pitfall:** `nohup` via SSH exec may not persist. If the process dies when SSH closes, use `setsid`:

```bash
ssh 100.70.18.84 -p 8022 'cd ~ && setsid python3 oneminai_server.py > ~/tmp/oneminai.log 2>&1 &'
```

### Step 4: Start 9Router (port 20128)

```bash
ssh 100.70.18.84 -p 8022 'cd ~ && PORT=20128 HOSTNAME=0.0.0.0 setsid node $(find /data/data/com.termux -name "server.js" -path "*/9router/*" 2>/dev/null | head -1) > ~/tmp/9router.log 2>&1 &'
sleep 3
ssh 100.70.18.84 -p 8022 'curl -s http://localhost:20128/v1/models | python3 -c "import sys,json; print(len(json.load(sys.stdin).get(\"data\",[])),\"models\")"'
```

**Note:** 9Router may not auto-start. Only start if the user explicitly uses it from Termux.

### Step 5: Verify VPS → Termux connectivity

```bash
curl -s --max-time 10 http://100.70.18.84:9000/health
curl -s --max-time 10 http://127.0.0.1:12029/v1/models  # through tunnel
```

### Step 6: Verify tunnels are healthy

```bash
~/.hermes/scripts/tunnel-ensure.sh
```

The tunnel-ensure.sh script auto-recovers the termux-llm tunnel (port 12029 → Termux:20128) if the SSH tunnel died.

## Service Map

| Service | Termux Port | VPS Tunnel | VPS Direct | Purpose |
|---------|------------|------------|------------|---------|
| 1minai proxy | 9000 | — | `100.70.18.84:9000` | OpenAI-compatible proxy |
| 9Router | 20128 | `127.0.0.1:12029` | — | AI model aggregator |

## Key Files on Termux

| File | Purpose |
|------|---------|
| `~/oneminai_server.py` | 1minai proxy server |
| `~/koofr-hermes/server.py` | Koofr drive Flask app |
| `~/.env` | API keys (ONEMINAI_API_KEY, etc.) |
| `~/tmp/oneminai.log` | Proxy logs |
| `~/tmp/9router.log` | 9Router logs |

## Persistence (Termux:Boot)

To auto-start services on boot, create a Termux:Boot script:

```bash
mkdir -p ~/.termux/boot
cat > ~/.termux/boot/start-services.sh << 'EOF'
#!/data/data/com.termux/files/usr/bin/bash
termux-wake-lock
cd ~
nohup python3 oneminai_server.py > ~/tmp/oneminai.log 2>&1 &
EOF
chmod +x ~/.termux/boot/start-services.sh
```

Requires Termux:Boot app from F-Droid. Run once to register the boot hook.

## Common Failures

| Symptom | Cause | Fix |
|---------|-------|-----|
| SSH works, curl 9000 fails | Proxy not started | Step 3 |
| `No such file or directory` on /tmp | Termux has no /tmp | Use `~/tmp` |
| Process dies when SSH closes | nohup not persisting | Use `setsid` instead |
| Tunnel 12029 returns 9Router | By design (port 20128) | Normal — termux-llm tunnel → 9Router |
| `python3: command not found` | Wrong PATH | Use full path or `source ~/.bashrc` first |

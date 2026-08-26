---
name: ssh-vps-explorer
description: Navigate, deploy, and optimize applications on Linux VPS servers via SSH. Covers connection patterns, Docker/Coolify deployment, performance tuning, and maintenance workflows. Use when managing remote VPS instances, deploying applications, or troubleshooting server performance.
category: devops
tags:
  - vps
  - ssh
  - docker
  - coolify
  - deployment
  - performance
  - monitoring
triggers:
  - "Deploy to VPS"
  - "Check VPS resources"
  - "SSH into server"
  - "Optimize VPS performance"
  - "Monitor VPS health"
---

# SSH VPS Explorer — Navigation, Deployment & Optimization

Complete guide for managing Linux VPS servers via SSH. Covers connection patterns, application deployment (Docker, Coolify, direct), performance monitoring, and maintenance workflows.

## TL;DR

```bash
# Quick connection (key-based)
ssh -i ~/.ssh/<keyname> <user>@<vps-ip>

# Resource snapshot
ssh -i ~/.ssh/<keyname> <user>@<vps-ip> "free -h && df -h / && uptime"

# Docker containers
ssh -i ~/.ssh/<keyname> <user>@<vps-ip> "sudo docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}'"

# Coolify apps
ssh -i ~/.ssh/<keyname> <user>@<vps-ip> "sudo docker ps | grep coolify"
```

---

## Phase 1: SSH Connection Patterns

### Standard Key-Based Auth
```bash
# First-time connection (accept host key)
ssh -o StrictHostKeyChecking=accept-new <user>@<vps-ip>

# Subsequent connections
ssh -i ~/.ssh/<keyname> <user>@<vps-ip>

# With timeout (for automation)
ssh -o ConnectTimeout=10 -o StrictHostKeyChecking=no <user>@<vps-ip>
```

### One-Liner Commands (No Interactive Shell)
```bash
# Single command execution
ssh -i ~/.ssh/<ssh-key> <user>@<vps-ip> "free -h"

# Multiple commands (semicolon-separated)
ssh -i ~/.ssh/<ssh-key> <user>@<vps-ip> "uptime; free -h; df -h /"

# With sudo (if configured)
ssh -i ~/.ssh/<ssh-key> <user>@<vps-ip> "sudo docker ps"
```

### Paramiko Python SSH (For Automation)
```python
import paramiko

client = paramiko.SSHClient()
client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
client.connect('<vps-ip>', username='<user>', key_filename='~/.ssh/<keyname>', timeout=10)

# Execute command
stdin, stdout, stderr = client.exec_command('docker ps --format "table {{.Names}}\t{{.Status}}"')
print(stdout.read().decode())

# Write file to remote
script = b'#!/bin/bash\necho "hello"\n'
stdin, stdout, stderr = client.exec_command('cat > /tmp/script.sh && bash /tmp/script.sh')
stdin.write(script)
stdin.channel.shutdown_write()

client.close()
```

### SSH Tunneling (For Localhost-Only Services)
```bash
# One-shot tunnel for testing
ssh -N -L 12028:localhost:20128 <user>@<vps-ip>

# Access tunneled service locally
curl http://127.0.0.1:12028/v1/models
```

---

## Phase 2: VPS Navigation & Discovery

### Quick Resource Snapshot
```bash
# All-in-one health check
ssh -i ~/.ssh/<ssh-key> <user>@<vps-ip> "echo '=== MEMORY ===' && free -h && echo '=== DISK ===' && df -h / && echo '=== LOAD ===' && uptime && echo '=== DOCKER ===' && sudo docker ps --format 'table {{.Names}}\t{{.Status}}'"
```

### Top Memory Consumers
```bash
# Process memory usage (RSS in MB)
ssh -i ~/.ssh/<ssh-key> <user>@<vps-ip> "ps aux --sort=-%mem | head -10 | awk '{printf \"%s: %.0fMB (%.1f%%)\n\", \$11, \$6/1024, \$4}'"
```

### Docker Container Audit
```bash
# List all containers with ports
ssh -i ~/.ssh/<ssh-key> <user>@<vps-ip> "sudo docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'"

# Container resource usage
ssh -i ~/.ssh/<ssh-key> <user>@<vps-ip> "sudo docker stats --no-stream --format 'table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}'"

# Docker disk usage
ssh -i ~/.ssh/<ssh-key> <user>@<vps-ip> "sudo docker system df"
```

### Coolify-Specific Commands
```bash
# List Coolify-managed containers
ssh -i ~/.ssh/<ssh-key> <user>@<vps-ip> "sudo docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}' | grep -E 'coolify|ekokwsg|eg00g8k'"

# Coolify dashboard access (internal only)
ssh -i ~/.ssh/<ssh-key> <user>@<vps-ip> "curl -s http://localhost:8000 | head -5"

# List deployed applications via container labels
ssh -i ~/.ssh/<ssh-key> <user>@<vps-ip> "sudo docker ps --format '{{.Names}}' | xargs -I{} sudo docker inspect {} --format '{{.Config.Labels}}' 2>/dev/null | grep coolify.name"
```

### Filesystem Navigation
```bash
# Large directories in home
ssh -i ~/.ssh/<ssh-key> <user>@<vps-ip> "du -xhd1 /home --exclude=.npm --exclude=.cache 2>/dev/null | sort -rh | head -20"

# Docker artifacts location
ssh -i ~/.ssh/<ssh-key> <user>@<vps-ip> "ls -la /artifacts/ 2>/dev/null | head -20"

# System logs
ssh -i ~/.ssh/<ssh-key> <user>@<vps-ip> "journalctl --since '1 hour ago' --no-pager | tail -30"
```

---

## Phase 3: Application Deployment

### Method 1: Direct Docker Compose (Manual)
```bash
# Create deployment directory
ssh -i ~/.ssh/<ssh-key> <user>@<vps-ip> "mkdir -p ~/apps/myapp && cd ~/apps/myapp"

# Create docker-compose.yaml
ssh -i ~/.ssh/<ssh-key> <user>@<vps-ip> "cat > ~/apps/myapp/docker-compose.yaml << 'EOF'
version: '3.8'
services:
  web:
    image: nginx:latest
    ports:
      - \"8080:80\"
    restart: unless-stopped
EOF"

# Deploy
ssh -i ~/.ssh/<ssh-key> <user>@<vps-ip> "cd ~/apps/myapp && sudo docker compose up -d"

# View logs
ssh -i ~/.ssh/<ssh-key> <user>@<vps-ip> "sudo docker compose -f ~/apps/myapp/docker-compose.yaml logs -f"
```

### Method 2: Coolify Deployment (Recommended for Production)
Coolify provides a web dashboard at `http://localhost:8000` (internal only).

**Deployment Flow:**
1. Access Coolify dashboard via SSH tunnel or VPS console
2. Connect GitHub repository
3. Select deployment type (Docker Compose, Dockerfile, etc.)
4. Configure environment variables and domains
5. Deploy → Coolify handles Docker + Traefik routing

**Coolify Architecture:**
```
┌─────────────────┐     ┌─────────────────┐
│   Coolify UI    │────▶│  Coolify API    │
│  (localhost:8000)│     │   (port 8080)   │
└─────────────────┘     └────────┬────────┘
                                 │
                    ┌────────────┼────────────┐
                    ▼            ▼            ▼
              ┌─────────┐  ┌─────────┐  ┌─────────┐
              │  App 1  │  │  App 2  │  │  App 3  │
              │ (port9000)│ │(port3000)│ │(port8002)│
              └─────────┘  └─────────┘  └─────────┘
                    │            │            │
                    └────────────┼────────────┘
                             ▼
                      ┌─────────────┐
                      │  Traefik    │
                      │ (Reverse   │
                      │  Proxy)     │
                      └─────────────┘
                             │
                     External Domains
```

**Existing Coolify Applications (<vps-ip>):**
| Application | Domain | Port | Type |
|-------------|--------|------|------|
| fastapi-deployable | oneminfallback.<domain> | 9000 | FastAPI |
| biograph-v15-fallbacks | biographai.<domain> | 3000 | Next.js/Node |
| paddleocr-api | paddle_away.<domain> | 8002 | PaddleOCR |
| fastapi-nomic-atlas-server | dock-nomic-atlas.<domain> | 10000 | FastAPI + Nomic |

### Method 3: Hostinger VPS API (No SSH Required)
Use the `hostinger-vps` MCP server to deploy Docker projects without SSH:

```python
# Deploy from raw YAML content
mcp_hostinger_vps_create_new_project_v1(
    virtualMachineId=<vps-id>,
    project_name="my-app",
    content="""
version: '3.8'
services:
  web:
    image: nginx:latest
    ports:
      - "80:80"
"""
)

# Deploy from GitHub repo (auto-fetches docker-compose.yaml)
mcp_hostinger_vps_create_new_project_v1(
    virtualMachineId=<vps-id>,
    project_name="my-app",
    content="https://github.com/user/repo"
)

# Management commands
mcp_hostinger_vps_get_project_list_v1(virtualMachineId=<vps-id>)
mcp_hostinger_vps_get_project_logs_v1(virtualMachineId=<vps-id>, project_name="my-app")
mcp_hostinger_vps_start_project_v1(virtualMachineId=<vps-id>, project_name="my-app")
mcp_hostinger_vps_stop_project_v1(virtualMachineId=<vps-id>, project_name="my-app")
```

---

## Phase 4: Performance Optimization

### Memory Optimization
```bash
# Clear page cache (read-only, safe)
ssh -i ~/.ssh/<ssh-key> <user>@<vps-ip> "sudo sync && echo 3 | sudo tee /proc/sys/vm/drop_caches"

# Identify memory hogs
ssh -i ~/.ssh/<ssh-key> <user>@<vps-ip> "ps aux --sort=-%mem | head -10"

# Check for memory leaks (compare over time)
ssh -i ~/.ssh/<ssh-key> <user>@<vps-ip> "free -m && sleep 60 && free -m"
```

### Disk Cleanup (Safe Tiers)
```bash
# 🟢 Tier 1: No-risk cache cleanup
ssh -i ~/.ssh/<ssh-key> <user>@<vps-ip> "
  sudo apt clean &&
  sudo journalctl --vacuum-time=3d &&
  rm -rf ~/.cache/uv/ &&
  pip cache purge 2>/dev/null || true
"

# 🟡 Tier 2: Safe with verification
ssh -i ~/.ssh/<ssh-key> <user>@<vps-ip> "
  docker system prune -f &&
  docker image prune -af
"

# 🔴 Tier 3: Needs user confirmation
# Large logs, old kernels, unused packages
```

### CPU & Load Optimization
```bash
# Check load average vs CPU cores
ssh -i ~/.ssh/<ssh-key> <user>@<vps-ip> "nproc && uptime"

# Identify CPU-intensive processes
ssh -i ~/.ssh/<ssh-key> <user>@<vps-ip> "top -bn1 | head -15"

# Check for runaway processes
ssh -i ~/.ssh/<ssh-key> <user>@<vps-ip> "ps aux --sort=-%cpu | head -10"
```

### Docker Optimization
```bash
# Prune unused resources
ssh -i ~/.ssh/<ssh-key> <user>@<vps-ip> "sudo docker system prune -af"

# Check container resource limits
ssh -i ~/.ssh/<ssh-key> <user>@<vps-ip> "sudo docker inspect --format='{{.Name}}: CPU={{.HostConfig.NanoCpus}} Mem={{.HostConfig.Memory}}' \$(sudo docker ps -q)"

# Enable cgroup v2 (if not already)
ssh -i ~/.ssh/<ssh-key> <user>@<vps-ip> "cat /proc/sys/kernel/cgroups_enabled"
```

---

## Phase 5: Monitoring & Maintenance

### Automated Resource Monitoring
The `server-resource-monitor` cron runs every 30 minutes via `vps-monitor.sh`:

```bash
# Script location
~/.hermes/scripts/vps-monitor.sh

# Cron job ID
b82d5c86b614 (server-resource-monitor)

# Schedule
*/30 * * * *

# Delivery
origin (Telegram DM)
```

**Monitor Script Commands:**
- `free -m` → Memory usage
- `df -h /` → Disk usage
- `uptime` → Load average
- `ps aux --sort=-%mem` → Top 3 memory processes

### Manual Health Check Template
```bash
# Complete health check (run as one command)
ssh -i ~/.ssh/<ssh-key> <user>@<vps-ip> "
  echo '=== SYSTEM ===' && uptime &&
  echo '=== MEMORY ===' && free -h &&
  echo '=== DISK ===' && df -h / &&
  echo '=== DOCKER ===' && sudo docker ps --format 'table {{.Names}}\t{{.Status}}' &&
  echo '=== TOP PROCESSES ===' && ps aux --sort=-%mem | head -5
"
```

### Log Analysis
```bash
# System logs (last hour)
ssh -i ~/.ssh/<ssh-key> <user>@<vps-ip> "journalctl --since '1 hour ago' --no-pager | tail -50"

# Docker container logs
ssh -i ~/.ssh/<ssh-key> <user>@<vps-ip> "sudo docker logs --since 1h <container-name> 2>&1 | tail -30"

# Coolify logs
ssh -i ~/.ssh/<ssh-key> <user>@<vps-ip> "sudo docker logs --since 1h coolify 2>&1 | tail -30"
```

---

## Phase 6: Troubleshooting

### SSH Connection Issues
```bash
# Test port connectivity
nc -zv <vps-ip> 22

# Verbose SSH output (diagnose handshake issues)
ssh -v -i ~/.ssh/<ssh-key> <user>@<vps-ip> "hostname"

# Check if SSH is running on remote
ssh -i ~/.ssh/<ssh-key> <user>@<vps-ip> "sudo systemctl status sshd"
```

### Docker Issues
```bash
# Check Docker daemon status
ssh -i ~/.ssh/<ssh-key> <user>@<vps-ip> "sudo systemctl status docker"

# Restart Docker (if needed)
ssh -i ~/.ssh/<ssh-key> <user>@<vps-ip> "sudo systemctl restart docker"

# Check for orphaned containers
ssh -i ~/.ssh/<ssh-key> <user>@<vps-ip> "sudo docker ps -a | grep -i dead"
```

### Coolify Issues
```bash
# Check Coolify services
ssh -i ~/.ssh/<ssh-key> <user>@<vps-ip> "sudo docker ps | grep coolify"

# Restart Coolify (if dashboard unresponsive)
ssh -i ~/.ssh/<ssh-key> <user>@<vps-ip> "sudo docker restart coolify coolify-db coolify-redis"

# Check Coolify API
ssh -i ~/.ssh/<ssh-key> <user>@<vps-ip> "curl -s http://localhost:8000/api/v1/version"
```

### Network Issues
```bash
# Test external connectivity
ssh -i ~/.ssh/<ssh-key> <user>@<vps-ip> "curl -s --max-time 10 https://cloudflare.com | head -1"

# Check DNS resolution
ssh -i ~/.ssh/<ssh-key> <user>@<vps-ip> "nslookup example.com"

# Check firewall rules
ssh -i ~/.ssh/<ssh-key> <user>@<vps-ip> "sudo iptables -L -n | head -20"
```

---

## Quick Reference Commands

### Daily Operations
```bash
# Check VPS status
ssh -i ~/.ssh/<ssh-key> <user>@<vps-ip> "uptime && free -h && df -h /"

# List Docker containers
ssh -i ~/.ssh/<ssh-key> <user>@<vps-ip> "sudo docker ps"

# View Coolify apps
ssh -i ~/.ssh/<ssh-key> <user>@<vps-ip> "sudo docker ps | grep -E 'coolify|ekokwsg|eg00g8k'"

# Check logs for specific app
ssh -i ~/.ssh/<ssh-key> <user>@<vps-ip> "sudo docker logs -f <container-name>"
```

### Deployment Commands
```bash
# Deploy new Docker app
mkdir -p ~/apps/myapp && cd ~/apps/myapp
cat > docker-compose.yaml << 'EOF'
version: '3.8'
services:
  web:
    image: nginx:latest
    ports:
      - "8080:80"
EOF
sudo docker compose up -d

# Update existing app
cd ~/apps/myapp && sudo docker compose pull && sudo docker compose up -d

# Rollback to previous version
sudo docker compose down && sudo docker image prune -af && sudo docker compose up -d
```

### Maintenance Commands
```bash
# Clean system caches
sudo apt clean && sudo journalctl --vacuum-time=3d

# Prune Docker resources
sudo docker system prune -af

# Check for security updates
sudo apt list --upgradable | head -20

# Reboot (if kernel updated)
sudo shutdown -r +5 "Scheduled reboot for updates"
```

---

## VPS-Specific Notes (<vps-ip>)

### Server Details
- **Hostname:** <vps-hostname>
- **IP:** <vps-ip>
- **Plan:** KVM 2 (2 CPU, 8GB RAM, 100GB disk)
- **OS:** Ubuntu 24.04 LTS
- **SSH User:** shark
- **SSH Key:** `~/.ssh/<ssh-key>`

### Coolify Setup
- **Dashboard:** http://localhost:8000 (internal only)
- **Proxy:** Traefik v3.6.5 (ports 80, 443)
- **Database:** PostgreSQL 15 (coolify-db)
- **Cache:** Redis 7 (coolify-redis)

### Deployed Applications
All apps use `<domain>` subdomains with automatic HTTPS:
- `oneminfallback.<domain>` → FastAPI (port 9000)
- `biographai.<domain>` → Next.js (port 3000)
- `paddle_away.<domain>` → PaddleOCR (port 8002)
- `dock-nomic-atlas.<domain>` → Nomic Atlas (port 10000)

---

## Related Skills

- `devops/ssh-mastery` — SSH connection patterns, tunneling, authentication
- `devops/server-diagnostics` — Resource audits, disk cleanup, health checks
- `mcp/hostinger-mcp-nav` — Hostinger API for VPS management without SSH

---

## Pitfalls

- **SSH key permissions:** Ensure private key is `600` (`chmod 600 ~/.ssh/<ssh-key>`)
- **Docker sudo:** Most Docker commands require `sudo` unless user is in `docker` group
- **Coolify internal only:** Dashboard is not externally accessible; use SSH tunnel or VPS console
- **Disk space during deployments:** Ensure <85% disk usage before pulling/deploying large images
- **Orphaned Docker containers:** After crashes, stale containers may persist; use `docker system prune` to clean
- **Traefik routing:** New apps need proper labels for automatic HTTPS; check Traefik config
- **SSH timeout in automation:** Always use `-o ConnectTimeout=10` for non-interactive scripts
- **Paramiko quoting:** Complex commands with nested quotes may break; prefer writing scripts to remote first

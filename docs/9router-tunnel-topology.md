# 9router Tunnel Topology

Dictionary-style reference for local SSH tunnels and their remote targets.

## Entries

- `12028` -> `<ammara-ip>:20128` (<ammara-hostname>, user: `<user>`, SSH: 22)
  - Role: 9router-pc / op
  - Hermes provider: `9router-op`
  - Hermes base_url: `http://127.0.0.1:12028/v1`

- `12029` -> `<termux-ip>:8022` -> `localhost:20128` (<termux-hostname>, user: `<user>`)
  - Role: termux-llm
  - Hermes provider usage: local-only Termux endpoint

## Health Signals

- Listening: `ss -ltnp | grep ':<LOCAL_PORT> '`
- API health: `curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:<LOCAL_PORT>/v1/models`
- Remote service: `curl -s http://127.0.0.1:<REMOTE_PORT>/v1/models` over SSH

## Pitfalls

1. Do not assume `9router-pc` is reachable directly. It may be offline in Tailscale. Only reachable via <ammara-hostname>.
2. Do not assume one tunnel failure means all tunnels are down. Test each local port independently.
3. Do not edit `~/.hermes/config.yaml` directly. Use `hermes config set providers.<name>.base_url http://127.0.0.1:<LOCAL_PORT>/v1`.
4. Do not retry Tunnel layer when Tailscale or SSH layer is down.

## Automated Recovery

Use `scripts/tunnel-ensure.sh` for idempotent tunnel recovery. See the script header for usage.

## Correction Log

- 2026-06-19: `12028` was mislabeled. Corrected target mapping.

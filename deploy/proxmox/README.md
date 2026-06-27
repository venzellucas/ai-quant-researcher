# Deploying the AI Quant Researcher on a hardened Proxmox LXC

## Quickest path: the bootstrap scripts (recommended)

Two scripts do everything. Your secrets only ever live inside the container.

```bash
# 1) get this repo onto the Proxmox host (clone, or rsync/scp from your Mac)
git clone git@github.com:venzellucas/ai-quant-researcher.git
cd ai-quant-researcher

# 2) create + harden + load the container (no secrets, doesn't start the service)
sudo IPADDR=192.168.1.50/24 GATEWAY=192.168.1.1 ./deploy/bootstrap_host.sh
#    (override CTID / STORAGE / BRIDGE / CORES / MEMORY / DISK via env as needed)

# 3) finish inside the container — this is where you type your two secrets
pct enter 105
cd /opt/ai-quant-researcher
./deploy/bootstrap_ct.sh
```

`bootstrap_host.sh` creates an unprivileged, no-nesting LXC with a static IP and
public DNS, installs the egress-only firewall, injects the code straight from the
checkout (the container never needs GitHub), and installs deps + the systemd unit.
`bootstrap_ct.sh` prompts silently for the OpenRouter key + Telegram token, writes
`.env` (root:600, never echoed), verifies it with a test Telegram message, and
starts the service.

The manual steps below are the same thing spelled out, for reference.

## 1. Create an unprivileged container

```bash
# on the Proxmox host (adjust CTID / storage / bridge to your homelab)
pct create 105 local:vztmpl/debian-12-standard_*.tar.zst \
  --hostname aqr \
  --cores 2 --memory 4096 --swap 512 \
  --unprivileged 1 \
  --features nesting=0 \
  --net0 name=eth0,bridge=vmbr0,ip=192.168.x.50/24,gw=192.168.x.1,firewall=1 \
  --nameserver 1.1.1.1 \
  --onboot 1
```

Key choices that enforce the "hard restraints":

- **`--unprivileged 1`** — root inside the container maps to an unprivileged host
  UID, so a process in the container is *nobody* on the host. This is the
  container-escape boundary you asked about: an unprivileged LXC cannot
  trivially become host root.
- **`--features nesting=0`** and **no host bind-mounts** — don't hand the agent
  any extra capability or a window into the host filesystem.
- **Static IP + `--nameserver 1.1.1.1`** — no dependency on the LAN's DHCP or
  internal DNS (AdGuard), so the firewall can block all private traffic cleanly.
- **`firewall=1`** on the NIC — required for the per-CT firewall below to apply.

## 2. Apply the network firewall (egress-only, no east-west, no host)

Copy `CTID.fw.example` to `/etc/pve/firewall/105.fw` on the host. Ensure the
Datacenter firewall is enabled (Datacenter → Firewall → Options → Firewall: Yes).

## 3. Verify the restraints

```bash
pct exec 105 -- sh -c 'curl -sS -o /dev/null -w "openrouter:%{http_code}\n" https://openrouter.ai/api/v1/models'  # should be 200
pct exec 105 -- ping -c1 -W2 192.168.x.1   # gateway ping may fail (fine)
pct exec 105 -- sh -c 'curl -sS -m3 https://<another-container-ip> ; echo rc=$?'  # should TIME OUT / fail
pct exec 105 -- sh -c 'curl -sS -m3 https://<proxmox-host-ip>:8006 ; echo rc=$?'  # should fail
```

## 4. Install the app

```bash
pct exec 105 -- bash -lc '
  apt-get update && apt-get install -y python3 python3-venv git
  git clone <repo> /opt/ai-quant-researcher
  cd /opt/ai-quant-researcher
  python3 -m venv .venv && .venv/bin/pip install -e .
  useradd -r -s /usr/sbin/nologin aqr || true
  install -d -o aqr /opt/ai-quant-researcher/data
'
# put your secrets in /opt/ai-quant-researcher/.env (chmod 600, owner aqr)
pct exec 105 -- bash -lc '
  cp deploy/systemd/ai-quant-researcher.service /etc/systemd/system/
  systemctl daemon-reload && systemctl enable --now ai-quant-researcher
  journalctl -u ai-quant-researcher -f
'
```

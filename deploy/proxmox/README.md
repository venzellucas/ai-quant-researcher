# Deploying the AI Quant Researcher on a hardened Proxmox LXC

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

#!/usr/bin/env bash
# Phase 3 — run on the PROXMOX HOST, from a checkout of this repo.
#
# Creates a hardened, egress-only, unprivileged LXC, injects the code straight
# from this checkout (so the container needs NO GitHub access), and installs the
# deps + systemd unit. It does NOT touch secrets and does NOT start the service.
# Finish by running deploy/bootstrap_ct.sh *inside* the container.
#
# Override any setting via env, e.g.:  CTID=106 STORAGE=tank IPADDR=192.168.1.50/24 ./deploy/bootstrap_host.sh
set -euo pipefail

CTID="${CTID:-105}"
CT_HOSTNAME="${CT_HOSTNAME:-aqr}"
CORES="${CORES:-2}"
MEMORY="${MEMORY:-4096}"
SWAP="${SWAP:-512}"
DISK="${DISK:-8}"                            # GB
STORAGE="${STORAGE:-local-lvm}"              # rootfs storage pool
TEMPLATE_STORAGE="${TEMPLATE_STORAGE:-local}"
TEMPLATE_VOLID="${TEMPLATE_VOLID:-}"         # auto-detected if empty
BRIDGE="${BRIDGE:-vmbr0}"
IPADDR="${IPADDR:-}"                         # CIDR, e.g. 192.168.1.50/24 (required)
GATEWAY="${GATEWAY:-}"                       # e.g. 192.168.1.1 (required)
DNS="${DNS:-1.1.1.1}"
APP_DIR="/opt/ai-quant-researcher"

die() { echo "ERROR: $*" >&2; exit 1; }
command -v pct >/dev/null || die "pct not found — run this on the Proxmox host"
[ "$(id -u)" -eq 0 ] || die "run as root"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

[ -n "$IPADDR" ]  || read -rp "Static IP for the container (CIDR, e.g. 192.168.1.50/24): " IPADDR
[ -n "$GATEWAY" ] || read -rp "Gateway IP (e.g. 192.168.1.1): " GATEWAY
pct status "$CTID" >/dev/null 2>&1 && die "CTID $CTID already exists — set CTID=<free id>"

if [ -z "$TEMPLATE_VOLID" ]; then
  TEMPLATE_VOLID="$(pveam list "$TEMPLATE_STORAGE" 2>/dev/null | awk '/debian-12-standard/{print $1}' | sort | tail -1 || true)"
  if [ -z "$TEMPLATE_VOLID" ]; then
    echo "==> no debian-12 template on '$TEMPLATE_STORAGE'; downloading…"
    pveam update >/dev/null 2>&1 || true
    NAME="$(pveam available --section system | awk '/debian-12-standard/{print $2}' | sort | tail -1)"
    [ -n "$NAME" ] || die "could not find a debian-12-standard template via pveam"
    pveam download "$TEMPLATE_STORAGE" "$NAME"
    TEMPLATE_VOLID="$(pveam list "$TEMPLATE_STORAGE" | awk '/debian-12-standard/{print $1}' | sort | tail -1)"
  fi
fi

cat <<EOF

About to create LXC $CTID:
  hostname    $CT_HOSTNAME
  template    $TEMPLATE_VOLID
  resources   ${CORES} vCPU / ${MEMORY}MB / ${SWAP}MB swap / ${DISK}GB ($STORAGE)
  network     $IPADDR  gw $GATEWAY  on $BRIDGE,  DNS $DNS,  firewall ON
  isolation   unprivileged, no nesting, egress-only (no LAN / no host reachability)
EOF
read -rp "Proceed? [y/N] " yn; [ "$yn" = y ] || [ "$yn" = Y ] || die "aborted"

echo "==> creating container"
pct create "$CTID" "$TEMPLATE_VOLID" \
  --hostname "$CT_HOSTNAME" \
  --cores "$CORES" --memory "$MEMORY" --swap "$SWAP" \
  --rootfs "${STORAGE}:${DISK}" \
  --unprivileged 1 --features nesting=0 \
  --net0 "name=eth0,bridge=${BRIDGE},ip=${IPADDR},gw=${GATEWAY},firewall=1" \
  --nameserver "$DNS" --onboot 1 --ostype debian

echo "==> installing egress-only firewall (/etc/pve/firewall/${CTID}.fw)"
cat > "/etc/pve/firewall/${CTID}.fw" <<'FW'
[OPTIONS]
enable: 1
policy_in: DROP
policy_out: DROP
log_level_in: nolog
log_level_out: nolog

[RULES]
# block all private space first (other guests, the host, the LAN)
OUT DROP -dest 10.0.0.0/8
OUT DROP -dest 172.16.0.0/12
OUT DROP -dest 192.168.0.0/16
OUT DROP -dest 100.64.0.0/10
OUT DROP -dest 169.254.0.0/16
# then allow internet egress (public destinations only, by elimination)
OUT ACCEPT -p tcp -dport 443
OUT ACCEPT -p tcp -dport 80
# DNS to public resolvers only
OUT ACCEPT -dest 1.1.1.1 -p udp -dport 53
OUT ACCEPT -dest 1.0.0.1 -p udp -dport 53
OUT ACCEPT -dest 1.1.1.1 -p tcp -dport 53
FW

if [ ! -f /etc/pve/firewall/cluster.fw ]; then
  printf '[OPTIONS]\nenable: 1\n' > /etc/pve/firewall/cluster.fw
  echo "==> enabled datacenter firewall (created cluster.fw)"
elif ! grep -qE '^[[:space:]]*enable:[[:space:]]*1' /etc/pve/firewall/cluster.fw; then
  echo "!! Datacenter firewall present but NOT enabled — per-CT rules won't apply."
  echo "   Set 'enable: 1' in /etc/pve/firewall/cluster.fw (Datacenter → Firewall → Options)."
fi

echo "==> starting container"
pct start "$CTID"

echo "==> waiting for DNS/network…"
for _ in $(seq 1 30); do
  pct exec "$CTID" -- getent hosts deb.debian.org >/dev/null 2>&1 && break
  sleep 2
done

echo "==> injecting code into ${APP_DIR} (no GitHub access needed in the CT)"
TARBALL="$(mktemp /tmp/aqr-src.XXXXXX.tar.gz)"
if [ -d "$REPO_DIR/.git" ]; then
  git -C "$REPO_DIR" archive --format=tar.gz -o "$TARBALL" HEAD
else
  tar -czf "$TARBALL" -C "$REPO_DIR" --exclude='.git' --exclude='.venv' --exclude='data' .
fi
pct exec "$CTID" -- mkdir -p "$APP_DIR"
pct push "$CTID" "$TARBALL" /tmp/aqr-src.tar.gz
pct exec "$CTID" -- tar -xzf /tmp/aqr-src.tar.gz -C "$APP_DIR"
pct exec "$CTID" -- rm -f /tmp/aqr-src.tar.gz
rm -f "$TARBALL"

echo "==> installing OS deps, venv, app, service user (no secrets, no start)"
pct exec "$CTID" -- bash -lc "
  set -e
  export DEBIAN_FRONTEND=noninteractive
  apt-get update -qq
  apt-get install -y -qq python3 python3-venv python3-pip ca-certificates >/dev/null
  id aqr >/dev/null 2>&1 || useradd -r -s /usr/sbin/nologin aqr
  python3 -m venv ${APP_DIR}/.venv
  ${APP_DIR}/.venv/bin/pip install -q --upgrade pip
  ${APP_DIR}/.venv/bin/pip install -q -e '${APP_DIR}[quant]'
  install -d -o aqr -g aqr ${APP_DIR}/data
  cp ${APP_DIR}/deploy/systemd/ai-quant-researcher.service /etc/systemd/system/
  systemctl daemon-reload
"

cat <<EOF

✅ Host setup done. Container $CTID is up, hardened, and loaded — but NOT started
   (no secrets yet). Finish inside the container, where your secrets stay:

     pct enter $CTID
     cd ${APP_DIR}
     ./deploy/bootstrap_ct.sh
EOF

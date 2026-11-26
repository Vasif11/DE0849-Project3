#!/usr/bin/env bash
# Phase 1 - Preparation and verification of the SDN host environment.
# Writes evidence to results/phase1/host_environment.txt
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/results/phase1"; mkdir -p "$OUT"
E="$OUT/host_environment.txt"; : > "$E"
say() { echo "$*" | tee -a "$E"; }

say "# Phase 1 host environment ($(date -Is))"
say "OS:      $(. /etc/os-release; echo "$PRETTY_NAME")"
say "Kernel:  $(uname -r)"
say "CPU:     $(nproc) cores"
say "Memory:  $(free -m | awk '/Mem:/{print $2" MB total, "$7" MB available"}')"
say "Python:  $(python3 --version 2>&1)"
say "Docker:  $(docker --version 2>&1)"
say "Mininet: $(mn --version 2>&1)"
say "OVS:     $(ovs-vsctl --version | head -1)"
say "iperf3:  $(iperf3 --version | head -1)"
say "tcpdump: $(tcpdump --version 2>&1 | head -1)"

say ""; say "## Open vSwitch service and kernel modules"
say "openvswitch-switch: $(systemctl is-active openvswitch-switch 2>&1)"
modprobe sch_tbf sch_netem 2>/dev/null
for m in openvswitch sch_tbf sch_netem veth; do
  if lsmod | grep -qw "$m"; then say "module $m: loaded"; else say "module $m: not loaded (built-in or missing)"; fi
done

say ""; say "## Docker operational check"
say "docker info (server): $(docker info --format '{{.ServerVersion}} / {{.OperatingSystem}}' 2>&1)"

say ""; say "## OVS bridge create/remove check"
ovs-vsctl add-br p3-check-br && say "bridge create: OK" || say "bridge create: FAIL"
ovs-vsctl br-exists p3-check-br && say "bridge exists: yes"
ovs-vsctl del-br p3-check-br && say "bridge remove: OK" || say "bridge remove: FAIL"
ovs-vsctl br-exists p3-check-br && say "bridge still exists: FAIL" || say "bridge gone after removal: OK"

say ""; say "## Mininet sanity (mn --test pingall, default topology)"
mn --test pingall 2>&1 | tee -a "$E" | tail -3
mn -c >/dev/null 2>&1
say ""; say "READY: $(command -v mn >/dev/null && command -v ovs-vsctl >/dev/null && command -v iperf3 >/dev/null && command -v tcpdump >/dev/null && echo yes || echo no)"

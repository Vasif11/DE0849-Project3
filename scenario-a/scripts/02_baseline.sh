#!/usr/bin/env bash
# Phase 2 - Baseline Mininet + OVS deployment WITHOUT an external controller.
# Two hosts on one OVS switch (standalone fail-mode), ping, then verify a clean OVS state.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/results/phase2"; mkdir -p "$OUT"
E="$OUT/baseline.txt"; : > "$E"
say() { echo "$*" | tee -a "$E"; }

mn -c >/dev/null 2>&1
say "# Phase 2 baseline ($(date -Is)) - 2 hosts, 1 OVS switch, no external controller"
# --controller none + standalone fail-mode: the OVS switch forwards autonomously (NORMAL action)
mn --topo single,2 --switch ovsk,failMode=standalone --controller none --test pingall 2>&1 | tee -a "$E" | grep -E 'Results|Ping|dropped|completed'
RC=${PIPESTATUS[0]}

say ""; say "## Cleanup verification"
mn -c >/dev/null 2>&1
say "OVS bridges left:        $(ovs-vsctl list-br | wc -l)"
say "stale mininet processes: $(pgrep -fc 'mininet:' || true)"
say "stale veth links:        $(ip -o link | grep -cE 's[0-9]+-eth|h[0-9]+-eth' || true)"
LEFT=$(ovs-vsctl list-br | wc -l)
if grep -q '0% dropped' "$E" && [ "$LEFT" = 0 ]; then say "BASELINE: PASS (0% loss, clean OVS state)"; else say "BASELINE: FAIL"; fi
